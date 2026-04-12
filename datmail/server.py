import datetime
from email.generator import BytesGenerator
import email.header
import email.parser
import email.utils
import io
import itertools
import json
import os
import re
import sys
import textwrap
import traceback
import uuid
from collections import OrderedDict, namedtuple

from emailtunnel import Envelope, InvalidRecipient, Message, SMTPForwarder, logger

import datmail.address
import datmail.headers
from datmail.address import GroupAlias  # PeriodAlias, DirectAlias,
from datmail.delivery_reports import parse_delivery_report
from datmail.dmarc import has_strict_dmarc_policy
from datmail.config import SRS_SECRET, CC_MAILLISTS, ADMINS
from datmail.django_api_client import DjangoAPIClient
from datmail.storage import Storage

RecipientGroup = namedtuple("RecipientGroup", "origin recipients".split())


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class DatForwarder(SMTPForwarder):
    REWRITE_FROM = True
    STRIP_HTML = False

    MAIL_FROM = 'mail@fredagscafeen.dk' # IT rewrites all emails to come from this to allow SES relay
    # MIKKEL: SES only allows relaying from known senders thus we have to use @fredagscafeen.dk
    # MAIL_FROM = None

    DOMAIN = "fredagscafeen.dk"
    DSN_RECIPIENT = "web@fredagscafeen.dk"

    ERROR_TEMPLATE = """
    This is the mail system of Fredagscaféen.

    The following exception was raised when processing the message below:

    {traceback}

    This exception will not be reported again before the mail server has
    been restarted.

    Envelope sender: {mailfrom}
    Envelope recipients: {rcpttos}
    Envelope message hidden.
    """

    ERROR_TEMPLATE_CONSTRUCTION = """
    This is the mail system of Fredagscaféen.

    The following exception was raised when CONSTRUCTING AN ENVELOPE:

    {traceback}

    This exception will not be reported again before the mail server has
    been restarted.

    Raw data:

    {data}
    """

    def __init__(self, *args, **kwargs):
        self.year = datetime.datetime.today().year
        self.exceptions = set()
        self.delivered = 0
        self.deliver_recipients = {}
        self.storage = Storage(bucket_name="mail-archive", region="fredagscafeen")
        self.api_client = DjangoAPIClient()
        super(DatForwarder, self).__init__(*args, **kwargs)

    def should_mailhole(self, message, recipient, sender):
        # Forward messages (do not sink to mailhole)
        return False

    def startup_log(self):
        logger.info(
            "DatForwarder listening on %s:%s, relaying to %s:%s, year %s",
            self.host,
            self.port,
            self.relay_host,
            self.relay_port,
            self.year,
        )

    def log_receipt(self, peer, envelope):
        mailfrom = envelope.mailfrom
        message = envelope.message
        envelope.received_at = datetime.datetime.now(datetime.timezone.utc)

        envelope_id = self.generate_uuid()

        try:
            message.add_header("X-Fredagscafeen-Envelope-ID", envelope_id)
        except Exception:
            logger.exception("Could not add X-Fredagscafeen-Envelope-ID header")

        logger.info("Handling new envelope with id: %s", envelope_id)

        self.store_envelope(envelope)

        if type(mailfrom) == str:
            sender = "<%s>" % mailfrom
        else:
            sender = repr(mailfrom)

        try:
            recipients_header = OrderedDict()
            for address, formatted, header in envelope.recipients():
                if address is not None:
                    address = re.sub(r"@fredagscafeen\.dk$", r"", address, 0, re.I)
                    recipients_header.setdefault(header, []).append(address)
            recipients = " ".join(
                "%s: <%s>" % (header, ">, <".join(group))
                for header, group in recipients_header.items()
            )
        except Exception as exn:
            logger.exception("Envelope.recipients() processing failed")
            rcpttos = envelope.rcpttos
            if type(rcpttos) == list and all(type(x) == str for x in rcpttos):
                rcpttos = [
                    re.sub(r"@fredagscafeen\.dk$", r"", address, 0, re.I)
                    for address in rcpttos
                ]
                if len(rcpttos) == 1:
                    recipients = "<%s>" % rcpttos[0]
                else:
                    recipients = ", ".join("<%s>" % x for x in rcpttos)
            else:
                recipients = repr(rcpttos)
            recipients = "To: " + recipients

        logger.info("Initial recipients: %s", recipients)

    def log_delivery(self, message, recipients, sender):
        if all("@" in rcpt for rcpt in recipients):
            parts = [rcpt.split("@", 1) for rcpt in recipients]
            parts.sort(key=lambda x: (x[1].lower(), x[0].lower()))
            by_domain = [
                (domain, [a[0] for a in aa])
                for domain, aa in itertools.groupby(parts, key=lambda x: x[1])
            ]
            recipients_string = ", ".join(
                "<%s@%s>" % (",".join(aa), domain) for domain, aa in by_domain
            )
        else:
            recipients_string = ", ".join("<%s>" % x for x in recipients)

        if len(recipients_string) > 200:
            age = self.deliver_recipients.get(recipients_string)
            if age is None or self.delivered - age > 40:
                self.deliver_recipients[recipients_string] = self.delivered
                recipients_string += " [%d]" % self.delivered
            else:
                recipients_string = "%s... [%d]" % (recipients_string[:197], age)

        self.delivered += 1

        logger.info("Forwarding to resolved recipients: %s", recipients_string)

    def handle_delivery_report(self, envelope):
        if envelope.mailfrom != "<>":
            return
        rcpttos = tuple(r.lower() for r in envelope.rcpttos)
        if rcpttos != (f"admin@{self.DOMAIN}",):
            return
        report = parse_delivery_report(envelope.message.message)
        if not report:
            return
        original_mailfrom = report.message.get("Return-Path") or "(unknown)"
        inner_envelope = Envelope(
            Message(report.message), original_mailfrom, report.recipients
        )
        description = summary = report.notification
        self.store_failed_envelope(envelope, description, summary, inner_envelope)
        logger.info("Failed to forward mail: %s", summary)
        return True

    def get_dsn_redirect_recipient(self, envelope):
        try:
            content_type = envelope.message.get_unique_header("Content-Type")
        except KeyError:
            content_type = ""

        ctype_report = content_type.startswith("multipart/report")
        ctype_delivery = "report-type=delivery-status" in content_type
        if ctype_report and ctype_delivery:
            return self.DSN_RECIPIENT

        subject_str = str(envelope.message.subject)
        delivery_status_subject = (
            "Delayed Mail" in subject_str
            or "Undelivered Mail Returned to Sender" in subject_str
        )
        if envelope.mailfrom == "<>" and delivery_status_subject:
            return self.DSN_RECIPIENT

    def reject(self, envelope):
        # Reject delivery status notifications not sent to admin@
        try:
            content_type = envelope.message.get_unique_header("Content-Type")
        except KeyError:
            content_type = ""
        ctype_report = content_type.startswith("multipart/report")
        ctype_delivery = "report-type=delivery-status" in content_type
        if ctype_report and ctype_delivery:
            return "Content-Type looks like a DSN"

        rcpttos = tuple(r.lower() for r in envelope.rcpttos)
        to_admin = rcpttos == (f"admin@{self.DOMAIN}",)
        subject = envelope.message.subject
        subject_str = str(subject)
        delivery_status_subject = (
            "Delayed Mail" in subject_str
            or "Undelivered Mail Returned to Sender" in subject_str
        )
        if to_admin and delivery_status_subject:
            return "Subject looks like a DSN"

        # Reject if a header is not encoded properly
        header_items = envelope.message.header_items()
        headers = [header for field, header in header_items]
        chunks = sum((header._chunks for header in headers), [])
        any_unknown = any(
            charset == email.charset.UNKNOWN8BIT for string, charset in chunks
        )
        if any_unknown:
            return "invalid header encoding"

        if envelope.mailfrom == "<>":
            # RFC 5321, 4.5.5. Messages with a Null Reverse-Path:
            # "[Automated email processors] SHOULD NOT reply to messages
            # with a null reverse-path, and they SHOULD NOT add a non-null
            # reverse-path, or change a null reverse-path to a non-null one,
            # to such messages when forwarding."
            # Since we would forward this message with a non-null reverse-path,
            # we should reject it instead.
            return "null reverse-path"

        n_from = len(envelope.message.get_all_headers("From"))
        if n_from != 1:
            return "wrong number of From-headers (%s)" % n_from
        if not envelope.from_domain:
            return "invalid From-header"
        if not self.REWRITE_FROM:
            dkim_sigs = envelope.message.get_all_headers("DKIM-Signature")
            # if envelope.strict_dmarc_policy and not dkim_sigs:
            #    return (
            #        "%s has strict DMARC policy, " % envelope.from_domain
            #        + "but message has no DKIM-Signature header"
            #    )

    def handle_envelope(self, envelope, peer):
        # Get year only once per envelope
        self.year = datetime.datetime.now().year
        dsn_recipient = self.get_dsn_redirect_recipient(envelope)
        if dsn_recipient:
            if tuple(r.lower() for r in envelope.rcpttos) != (dsn_recipient.lower(),):
                logger.info("Redirecting DSN to <%s>", dsn_recipient)
                envelope.rcpttos = [dsn_recipient]
            if not self.REWRITE_FROM and not self.STRIP_HTML:
                self.fix_headers(envelope.message)
            return super(DatForwarder, self).handle_envelope(envelope, peer)
        if self.handle_delivery_report(envelope):
            return
        envelope.from_domain = self.get_from_domain(envelope)

        # TODO: Fix strict dmarc policy and enable this
        # envelope.strict_dmarc_policy = self.strict_dmarc_policy(envelope)

        reject_reason = self.reject(envelope)
        if reject_reason:
            summary = "Rejected by DatForwarder.reject (%s)" % reject_reason
            logger.info("%s", summary)
            self.store_failed_envelope(envelope, summary, summary)
            self.report_dropped_mail(envelope, summary)
            return

        for rcptto in envelope.rcpttos:
            if f"@{self.DOMAIN}" in rcptto.lower():
                # Poor man's spam filter
                from_domain = envelope.from_domain.lower()
                if from_domain:
                    allowed_domains, blocked_domains = self.api_client.get_spamfilter()
                    if not any(
                        from_domain.endswith(tld) for tld in allowed_domains
                    ) or any(from_domain.endswith(tld) for tld in blocked_domains):
                        summary = "Rejected: spam filter triggered"
                        logger.info(
                            "%s: %s (%s) -> %s",
                            summary,
                            from_domain,
                            envelope.mailfrom,
                            rcptto,
                        )
                        self.store_failed_envelope(envelope, summary, summary)
                        self.report_dropped_mail(envelope, summary)
                        return

                # Check authorization for internal-only lists
                list_name = rcptto.split("@")[0]
                # If the envelope.mailfrom was rewritten by SRS, recover the original
                sender_email = self.extract_original_sender(envelope.mailfrom)
                if not self.is_sender_authorized_for_list(sender_email, list_name):
                    summary = "Rejected: sender not authorized for internal-only list"
                    logger.info(
                        "%s: %s (%s) -> %s",
                        summary,
                        sender_email,
                        envelope.mailfrom,
                        rcptto,
                    )
                    self.store_failed_envelope(envelope, summary, summary)
                    self.report_dropped_mail(envelope, summary)
                    return

        if CC_MAILLISTS:
            # Ensure CC for best@{self.DOMAIN}
            try:
                if any(r.lower() == f"best@{self.DOMAIN}" for r in envelope.rcpttos):
                    self._ensure_list_cc(envelope.message, "best")
            except Exception:
                logger.exception(f"Failed to add CC for best@{self.DOMAIN}")

            # Ensure CC for alle@{self.DOMAIN}
            try:
                if any(r.lower() == f"alle@{self.DOMAIN}" for r in envelope.rcpttos):
                    self._ensure_list_cc(envelope.message, "alle")
            except Exception:
                logger.exception(f"Failed to add CC for alle@{self.DOMAIN}")

        if not self.REWRITE_FROM and not self.STRIP_HTML:
            self.fix_headers(envelope.message)
        result = super(DatForwarder, self).handle_envelope(envelope, peer)
        return result

    def _ensure_list_cc(self, message, list_name):
        """
        Ensure 'datcafe-{list_name}.cs@maillist.au.dk' is included in the Cc header.
        Append to existing Cc if present; otherwise add a new Cc header.
        """
        target = f"datcafe-{list_name}.cs@maillist.au.dk"
        try:
            existing_cc = message.get_header("Cc")
        except KeyError:
            existing_cc = None

        if existing_cc:
            addrs = [
                addr.lower() for _, addr in email.utils.getaddresses([existing_cc])
            ]
            if target.lower() in addrs:
                return  # Already present
            new_cc = existing_cc + ", " + target
            message.set_unique_header("Cc", new_cc)
        else:
            message.add_header("Cc", target)

    def fix_headers(self, message):
        # Fix References: header that has been broken by Postfix.
        # If an email has a DKIM-Signature on the RFC5322.References header,
        # and Postfix breaks RFC5322.References into multiple lines because
        # some lines were longer than 990 bytes, then the DKIM-Signature
        # becomes invalid. Since no sane email provider would apply a
        # DKIM-Signature to a RFC5322.References header with erroneous
        # whitespace, we remove any erroneous whitespace, that is,
        # whitespace between two angle brackets <...>, from the header.
        references_header = message.get_all_headers("References")
        fixed_header = []
        for v in references_header:
            # Move space/newline in front of the '<'.
            v2 = re.sub(r"(<[^<> \n\r\t]*)([ \n\r\t]+)", r"\2\1", v)
            if v != v2:
                # We had to move some whitespace to fix the header,
                # so we may inadvertently have created new too-long lines.
                # Replace all whitespace with CR LF SP to avoid long lines.
                v2 = "\r\n ".join(v2.split())
            fixed_header.append(v2)
        if references_header == fixed_header:
            # No change required
            return
        # We had to fix RFC5322.References. In order to use set_unique_header
        # (to retain the position of the header in the message) there must be
        # only one RFC5322.References in the message.
        try:
            (v2,) = fixed_header
        except ValueError:
            # Write fixed_header to log.
            logger.exception("Multiple References-headers: %r", fixed_header)
            # I think multiple RFC5322.References headers is invalid,
            # but the RFC does not make it entirely clear.
            # On the other hand, who would have both multiple
            # RFC5322.References *and* header lines longer than 990 bytes?
            raise NotImplementedError(
                "Multiple References:-headers and some/all are invalid"
            )
        message.set_unique_header("References", v2)

    def get_from_domain(self, envelope):
        from_header = envelope.message.get_header("From", "") or ""
        from_header = str(from_header) if from_header else ""
        from_domain_mo = re.search(r"@([^ \t\n>]+)", from_header)
        if from_domain_mo:
            return from_domain_mo.group(1)

    def extract_original_sender(self, mailfrom):
        """
        Decode SRS-rewritten senders like:
            SRS0=HASH=TTL=orig-domain=orig-local@forwarder
        into orig-local@orig-domain; if not an SRS form, return the input.
        Surrounding angle brackets are tolerated.
        """
        try:
            if not isinstance(mailfrom, str):
                return mailfrom
            # Strip surrounding angle brackets if present
            m = mailfrom.strip()
            if m.startswith("<") and m.endswith(">"):
                m = m[1:-1].strip()
            # Split local part and domain
            if "@" not in m:
                return mailfrom
            local, domain = m.rsplit("@", 1)
            # If local part looks like SRS, try to recover original
            if local.upper().startswith("SRS"):
                parts = local.split("=")
                # Expect at least: SRS*, HASH, TTL, orig-domain, orig-local
                if len(parts) >= 3:
                    orig_local = parts[-1]
                    orig_domain = parts[-2]
                    return "%s@%s" % (orig_local, orig_domain)
        except Exception:
            # On any failure, fall back to the original string
            pass
        return mailfrom

    def strict_dmarc_policy(self, envelope):
        if envelope.from_domain:
            return has_strict_dmarc_policy(envelope.from_domain)

    def translate_recipient(self, rcptto):
        name, domain = rcptto.split("@")

        recipients, origin = datmail.address.translate_recipient(name, list_group_origins=True)
        if not recipients:
            logger.info("Invalid recipient: %s resolved to an empty list", name)
            raise InvalidRecipient(rcptto)
        recipients.sort(key=lambda r: origin[r])
        group_iter = itertools.groupby(recipients, key=lambda r: origin[r])
        groups = [
            RecipientGroup(origin=o, recipients=frozenset(group))
            for o, group in group_iter
        ]
        return groups

    def get_group_recipients(self, group):
        return group.recipients

    def is_sender_authorized_for_list(self, sender_email, list_name):
        """Check if sender is authorized to send to an internal-only list."""
        try:
            # Override internal-only if internal mail sender
            if f"@{self.DOMAIN}" in sender_email:
                return True
            
            try:
                list_info = self.api_client.get_mailinglist_info(list_name)  # Check if list exists and is internal-only
            except Exception:
                logger.exception(f"Error fetching mailing list info for {list_name}")
                return True  # Allow if we cannot fetch list info
            
            if list_info.get("isOnlyInternal") and list_info.get("members"):
                # List is internal-only, check if sender is a member
                members = list_info.get("members", [])
                return sender_email.lower() in [m.get("email", "").lower() for m in members]
            else:
                return True  # Not an internal-only list
        except Exception:
            logger.exception("Error checking sender authorization")
            return True  # Allow on error

    def get_envelope_mailfrom(self, envelope, recipients=None):
        # Prefer configured MAIL_FROM if set
        if self.MAIL_FROM is not None:
            return self.MAIL_FROM

        # Apply SRS when forwarding to external recipients to preserve SPF
        try:
            rcpts = recipients or envelope.rcpttos or []
            # If any recipient domain is not local, SRS-encode the MAIL FROM
            external = any(
                ("@" in r) and (r.lower().split("@", 1)[1] != self.DOMAIN.lower())
                for r in rcpts
            )
            if external and isinstance(envelope.mailfrom, str):
                return self.srs_encode(envelope.mailfrom)
        except Exception:
            logger.exception("SRS encoding failed; falling back to original MAIL FROM")
        return envelope.mailfrom

    def srs_encode(self, mailfrom):
        """
        Minimal SRS0 encoding:
        SRS0=HASH=orig-domain=orig-local@DOMAIN
        HASH is a short HMAC over [orig-local, orig-domain].
        """
        try:
            m = mailfrom.strip()
            if m.startswith("<") and m.endswith(">"):
                m = m[1:-1].strip()
            if "@" not in m:
                return mailfrom
            orig_local, orig_domain = m.rsplit("@", 1)
            import hmac, hashlib

            key = SRS_SECRET.encode("utf-8")
            data = ("%s@%s" % (orig_local, orig_domain)).encode("utf-8")
            digest = hmac.new(key, data, hashlib.sha256).hexdigest()
            # Truncate to keep it short
            h = digest[:10]
            return "SRS0=%s=%s=%s@%s" % (h, orig_domain, orig_local, self.DOMAIN)
        except Exception:
            logger.exception("srs_encode error")
            return mailfrom

    def get_extra_headers(self, envelope, group):
        sender = self.get_envelope_mailfrom(envelope)
        list_name = str(group.origin).lower()
        # is_group = isinstance(group.origin, GroupAlias)
        is_group = False
        headers = datmail.headers.get_extra_headers(sender, list_name, is_group)
        if self.REWRITE_FROM:
            orig_from = envelope.message.get_header("From")
            headers.append(("From", self.get_from_header(envelope, group)))
            if orig_from:
                headers.append(("Reply-To", orig_from))
        return headers

    def get_from_header(self, envelope, group):
        orig_from = envelope.message.get_header("From")
        orig_to = group.origin.name.lower()
        parsed = email.utils.getaddresses([orig_from])
        name = parsed[0][0]
        addr = self.MAIL_FROM or "mail@%s" % self.DOMAIN
        return email.utils.formataddr(("%s via %s" % (name, orig_to), addr))

    def forward(self, original_envelope, message, recipients, sender):
        if self.REWRITE_FROM or self.STRIP_HTML:
            del message.message["DKIM-Signature"]
        if self.STRIP_HTML:
            from emailtunnel.extract_text import get_body_text

            t = get_body_text(message.message)
            message.set_unique_header("Content-Type", "text/plain")
            del message.message["Content-Transfer-Encoding"]
            charset = email.charset.Charset("utf-8")
            charset.header_encoding = charset.body_encoding = email.charset.QP
            message.message.set_payload(t, charset=charset)
        # Use SRS-encoded MAIL FROM when delivering externally
        original_envelope.expanded_recipients = set(
            getattr(original_envelope, "expanded_recipients", set())
        )
        original_envelope.expanded_recipients.update(recipients)
        sender = self.get_envelope_mailfrom(original_envelope, recipients=recipients)
        self.report_processed_mail(
            original_envelope,
            getattr(original_envelope, "expanded_recipients", set()),
            self.get_report_mailing_list(original_envelope),
        )
        super().forward(original_envelope, message, recipients, sender)

    def log_invalid_recipient(self, envelope, exn):
        # Use logging.info instead of the default logging.error
        logger.info("Invalid recipient: %r", exn.args)

    def handle_invalid_recipient(self, envelope, exn):
        self.store_failed_envelope(envelope, str(exn), "Invalid recipient: %s" % exn)

    def handle_error(self, envelope, str_data):
        exc_value = sys.exc_info()[1]
        exc_typename = type(exc_value).__name__
        filename, line, function, text = traceback.extract_tb(sys.exc_info()[2])[0]

        tb = "".join(traceback.format_exc())
        if envelope:
            try:
                self.store_failed_envelope(
                    envelope, str(tb), "%s: %s" % (exc_typename, exc_value)
                )
            except:
                logger.exception("Could not store_failed_envelope")

        exc_key = (filename, line, exc_typename)

        if exc_key not in self.exceptions:
            self.exceptions.add(exc_key)
            self.forward_to_admin(envelope, str_data, tb)

    def forward_to_admin(self, envelope, str_data, tb):
        admin_emails, _ = datmail.address.get_admin_emails() # Fallback in case of django API failure

        sender = recipient = f"admin@{self.DOMAIN}"

        if envelope:
            subject = "[datmail] Unhandled exception in processing"
            body = textwrap.dedent(self.ERROR_TEMPLATE).format(
                traceback=tb, mailfrom=envelope.mailfrom, rcpttos=envelope.rcpttos
            )

        else:
            subject = "[datmail] Could not construct envelope"
            body = textwrap.dedent(self.ERROR_TEMPLATE_CONSTRUCTION).format(
                traceback=tb, data=str_data
            )

        admin_message = Message.compose(sender, recipient, subject, body)
        admin_message.add_header("Auto-Submitted", "auto-replied")

        try:
            headers = datmail.headers.get_extra_headers(
                sender, "datmailerror", is_group=True
            )
            for k, v in headers:
                admin_message.add_header(k, v)
        except Exception:
            logger.exception("Could not add extra headers in forward_to_admin")

        self.deliver(admin_message, admin_emails, sender)

    def generate_uuid(self):
        return str(uuid.uuid4())

    def get_request_uuid(self, envelope):
        return envelope.message.get_header("X-Fredagscafeen-Envelope-ID")

    def get_received_at(self, envelope):
        received_at = getattr(envelope, "received_at", None)
        if received_at is None:
            received_at = datetime.datetime.now(datetime.timezone.utc)
        elif received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=datetime.timezone.utc)
        return received_at.isoformat().replace("+00:00", "Z")

    def get_archive_object_name(self, envelope):
        return f"archive/{self.get_request_uuid(envelope)}.eml"

    def get_report_target(self, envelope):
        if envelope.rcpttos:
            return envelope.rcpttos[0]
        return ""

    def get_report_mailing_list(self, envelope):
        target = self.get_report_target(envelope)
        if f"@{self.DOMAIN}" not in target.lower():
            return None
        return target.split("@", 1)[0].lower()

    def report_processed_mail(self, envelope, expanded_recipients, mailing_list_name):
        if self.api_client is None:
            return
        payload = {
            "request_uuid": self.get_request_uuid(envelope),
            "received_at": self.get_received_at(envelope),
            "sender": self.extract_original_sender(envelope.mailfrom),
            "target": self.get_report_target(envelope),
            "mailing_list": mailing_list_name,
            "status": "PROCESSED",
            "reason": "",
            "s3_object_key": self.get_archive_object_name(envelope),
            "expanded_recipients": sorted(expanded_recipients),
        }
        try:
            self.api_client.upsert_incoming_mail(payload)
        except Exception:
            logger.exception("Could not report processed mail to Django")

    def report_dropped_mail(self, envelope, reason):
        if self.api_client is None:
            return
        payload = {
            "request_uuid": self.get_request_uuid(envelope),
            "received_at": self.get_received_at(envelope),
            "sender": self.extract_original_sender(envelope.mailfrom),
            "target": self.get_report_target(envelope),
            "mailing_list": self.get_report_mailing_list(envelope),
            "status": "DROPPED",
            "reason": reason,
            "s3_object_key": self.get_archive_object_name(envelope),
            "expanded_recipients": [],
        }
        try:
            self.api_client.upsert_incoming_mail(payload)
        except Exception:
            logger.exception("Could not report dropped mail to Django")

    def resend_archived_mail(self, request_uuid, target, sender, original_target):
        raw_eml = self.storage.get_object(f"archive/{request_uuid}.eml")
        parsed_message = email.parser.BytesParser().parsebytes(raw_eml)
        message = Message(parsed_message)
        envelope = Envelope(message, sender, [original_target])
        group = RecipientGroup(GroupAlias(original_target.split("@", 1)[0]), [target])
        for field, value in self.get_extra_headers(envelope, group):
            envelope.message.set_unique_header(field, value)
        self.forward(envelope, envelope.message, [target], sender)

    def get_raw_eml(self, message):
        """Helper to get the raw bytes of an email message."""
        # 'message' here is your emailtunnel.Message object
        # 'message.message' is the underlying email.message.Message
        out = io.BytesIO()
        gen = BytesGenerator(out)
        gen.flatten(message.message)
        return out.getvalue()
    
    def store_envelope(self, envelope):
        """Store the raw email in S3 for archival."""
        try:
            raw_eml = self.get_raw_eml(envelope.message)
            envelope_id = envelope.message.get_header("X-Fredagscafeen-Envelope-ID")
            object_name = f"archive/{envelope_id}.eml"
            self.storage.upload_object(raw_eml, object_name)
        except Exception as e:
            logger.error(f"Error storing envelope to S3: {e}")

    def store_failed_envelope(
        self, envelope, description, summary, inner_envelope=None
    ):
        now = now_string()

        try:
            os.mkdir("error")
        except FileExistsError:
            pass

        if inner_envelope is None:
            inner_envelope = envelope
        with open("error/%s.json" % now, "w") as fp:
            metadata = {
                "mailfrom": inner_envelope.mailfrom,
                "rcpttos": inner_envelope.rcpttos,
                "subject": str(inner_envelope.message.subject),
                "date": inner_envelope.message.get_header("Date"),
                "summary": summary,
            }
            json.dump(metadata, fp)

        with open("error/%s.txt" % now, "w") as fp:
            fp.write("From: %s\n" % inner_envelope.mailfrom)
            fp.write("To: %s\n" % inner_envelope.rcpttos)
            try:
                fp.write("Subject: %s\n" % inner_envelope.message.subject)
            except Exception:
                fp.write("Unknown subject\n")
            try:
                fp.write("Date: %s\n" % inner_envelope.message.get_header("Date"))
            except Exception:
                fp.write("Unknown date\n")
            fp.write("Summary: %s\n" % summary)
            fp.write("\n%s\n" % description)
