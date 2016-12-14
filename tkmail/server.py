import os
import re
import sys
import json
import logging
import datetime
import textwrap
import itertools
import traceback

import email.header

from emailtunnel import SMTPForwarder, Message, InvalidRecipient

import tkmail.address


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class TKForwarder(SMTPForwarder):
    ERROR_TEMPLATE = """
    This is the mail system of TAAGEKAMMERET.

    The following exception was raised when processing the message below:

    {traceback}

    This exception will not be reported again before the mail server has
    been restarted.

    Envelope sender: {mailfrom}
    Envelope recipients: {rcpttos}
    Envelope message:

    {message}
    """

    ERROR_TEMPLATE_CONSTRUCTION = """
    This is the mail system of TAAGEKAMMERET.

    The following exception was raised when CONSTRUCTING AN ENVELOPE:

    {traceback}

    This exception will not be reported again before the mail server has
    been restarted.

    Raw data:

    {data}
    """

    def __init__(self, *args, **kwargs):
        self.year = kwargs.pop('year')
        self.exceptions = set()
        self.delivered = 0
        self.deliver_recipients = {}
        super(TKForwarder, self).__init__(*args, **kwargs)

    def startup_log(self):
        logging.info(
            'TKForwarder listening on %s:%s, relaying to %s:%s, GF year %s',
            self.host, self.port, self.relay_host, self.relay_port, self.year)

    def log_receipt(self, peer, envelope):
        mailfrom = envelope.mailfrom
        rcpttos = envelope.rcpttos
        message = envelope.message

        if type(mailfrom) == str:
            sender = '<%s>' % mailfrom
        else:
            sender = repr(mailfrom)

        if type(rcpttos) == list and all(type(x) == str for x in rcpttos):
            rcpttos = [re.sub(r'@(T)AAGE(K)AMMERET\.dk$', r'@@\1\2', x,
                              0, re.I)
                       for x in rcpttos]
            if len(rcpttos) == 1:
                recipients = '<%s>' % rcpttos[0]
            else:
                recipients = ', '.join('<%s>' % x for x in rcpttos)
        else:
            recipients = repr(rcpttos)

        logging.info("Subject: %r From: %s To: %s",
                     str(message.subject), sender, recipients)

    def log_delivery(self, message, recipients, sender):
        if all('@' in rcpt for rcpt in recipients):
            parts = [rcpt.split('@', 1) for rcpt in recipients]
            parts.sort(key=lambda x: (x[1].lower(), x[0].lower()))
            by_domain = [
                (domain, [a[0] for a in aa])
                for domain, aa in itertools.groupby(
                    parts, key=lambda x: x[1])
            ]
            recipients_string = ', '.join(
                '<%s@%s>' % (','.join(aa), domain)
                for domain, aa in by_domain)
        else:
            recipients_string = ', '.join('<%s>' % x for x in recipients)

        if len(recipients_string) > 200:
            age = self.deliver_recipients.get(recipients_string)
            if age is None or self.delivered - age > 40:
                self.deliver_recipients[recipients_string] = self.delivered
                recipients_string += ' [%d]' % self.delivered
            else:
                recipients_string = '%s... [%d]' % (
                    recipients_string[:197], age)

        self.delivered += 1

        logging.info('Subject: %r To: %s',
                     str(message.subject), recipients_string)

    def reject(self, envelope):
        rcpttos = tuple(r.lower() for r in envelope.rcpttos)
        to_admin = rcpttos == ('admin@taagekammeret.dk',)

        subject = envelope.message.subject
        subject_str = str(subject)
        delivery_status_subject = (
            'Delayed Mail' in subject_str or
            'Undelivered Mail Returned to Sender' in subject_str)

        try:
            content_type = envelope.message.get_unique_header('Content-Type')
        except KeyError:
            content_type = ''
        ctype_report = content_type.startswith('multipart/report')
        ctype_delivery = 'report-type=delivery-status' in content_type

        header_items = envelope.message.header_items()
        headers = [header for field, header in header_items]
        chunks = sum((header._chunks for header in headers), [])
        any_unknown = any(charset == email.charset.UNKNOWN8BIT
                          for string, charset in chunks)

        return any((
            to_admin and delivery_status_subject,
            to_admin and ctype_report and ctype_delivery,
            any_unknown,
        ))

    def handle_envelope(self, envelope, peer):
        if self.reject(envelope):
            description = summary = 'Rejected due to TKForwarder.reject'
            self.store_failed_envelope(envelope, description, summary)

        else:
            return super(TKForwarder, self).handle_envelope(envelope, peer)

    def translate_subject(self, envelope):
        subject = envelope.message.subject
        subject_decoded = str(subject)

        if '[TK' in subject_decoded:
            # No change
            return None

        try:
            chunks = subject._chunks
        except AttributeError:
            logging.warning('envelope.message.subject does not have _chunks')
            chunks = email.header.decode_header(subject_decoded)

        # No space in '[TK]', since the chunks are joined by spaces.
        subject_chunks = [('[TK]', None)] + list(chunks)
        return email.header.make_header(subject_chunks)

    def translate_recipient(self, rcptto):
        name, domain = rcptto.split('@')
        recipients, origin = tkmail.address.translate_recipient(
            self.year, name, list_ids=True)
        if not recipients:
            logging.info("%s resolved to the empty list", name)
            raise InvalidRecipient(rcptto)
        recipients.sort(key=lambda r: origin[r])
        group_iter = itertools.groupby(recipients, key=lambda r: origin[r])
        groups = [(o, frozenset(group))
                  for o, group in group_iter]
        return groups

    def get_group_recipients(self, group):
        origin, recipients = group
        return recipients

    def get_envelope_mailfrom(self, envelope, recipients=None):
        return 'admin@TAAGEKAMMERET.dk'

    def get_sender_header(self, envelope, group):
        return self.get_envelope_mailfrom(envelope)

    def get_list_name(self, envelope, group):
        origin, recipients = group
        return origin.lower()

    def get_list_id_header(self, envelope, group):
        return '%s.TAAGEKAMMERET.dk' % self.get_list_name(envelope, group)

    def get_list_unsubscribe_header(self, envelope, group):
        origin, recipients = group
        sender = self.get_sender_header(envelope, group)
        o = self.get_list_name(envelope, group)
        return '<mailto:%s?subject=unsubscribe%%20%s>' % (sender, o)

    def get_list_help_header(self, envelope, group):
        origin, recipients = group
        sender = self.get_sender_header(envelope, group)
        return '<mailto:%s?subject=list-help>' % (sender,)

    def get_list_subscribe_header(self, envelope, group):
        origin, recipients = group
        sender = self.get_sender_header(envelope, group)
        o = self.get_list_name(envelope, group)
        return '<mailto:%s?subject=subscribe%%20%s>' % (sender, o)

    def log_invalid_recipient(self, envelope, exn):
        # Use logging.info instead of the default logging.error
        logging.info('Invalid recipient: %r', exn.args)

    def handle_invalid_recipient(self, envelope, exn):
        self.store_failed_envelope(
            envelope, str(exn), 'Invalid recipient: %s' % exn)

    def handle_error(self, envelope, str_data):
        exc_value = sys.exc_info()[1]
        exc_typename = type(exc_value).__name__
        filename, line, function, text = traceback.extract_tb(
            sys.exc_info()[2])[0]

        tb = ''.join(traceback.format_exc())
        if envelope:
            try:
                self.store_failed_envelope(
                    envelope, str(tb),
                    '%s: %s' % (exc_typename, exc_value))
            except:
                logging.exception("Could not store_failed_envelope")

        exc_key = (filename, line, exc_typename)

        if exc_key not in self.exceptions:
            self.exceptions.add(exc_key)
            self.forward_to_admin(envelope, str_data, tb)

    def forward_to_admin(self, envelope, str_data, tb):
        # admin_emails = tkmail.address.get_admin_emails()
        admin_emails = ['mathiasrav@gmail.com']

        sender = recipient = 'admin@TAAGEKAMMERET.dk'

        if envelope:
            subject = '[TK-mail] Unhandled exception in processing'
            body = textwrap.dedent(self.ERROR_TEMPLATE).format(
                traceback=tb, mailfrom=envelope.mailfrom,
                rcpttos=envelope.rcpttos, message=envelope.message)

        else:
            subject = '[TK-mail] Could not construct envelope'
            body = textwrap.dedent(self.ERROR_TEMPLATE_CONSTRUCTION).format(
                traceback=tb, data=str_data)

        admin_message = Message.compose(
            sender, recipient, subject, body)
        admin_message.add_header('Auto-Submitted', 'auto-replied')

        self.deliver(admin_message, admin_emails, sender)

    def store_failed_envelope(self, envelope, description, summary):
        now = now_string()

        try:
            os.mkdir('error')
        except FileExistsError:
            pass

        with open('error/%s.mail' % now, 'wb') as fp:
            fp.write(envelope.message.as_bytes())

        with open('error/%s.json' % now, 'w') as fp:
            metadata = {
                'mailfrom': envelope.mailfrom,
                'rcpttos': envelope.rcpttos,
                'subject': str(envelope.message.subject),
                'date': envelope.message.get_header('Date'),
                'summary': summary,
            }
            json.dump(metadata, fp)

        with open('error/%s.txt' % now, 'w') as fp:
            fp.write('From %s\n' % envelope.mailfrom)
            fp.write('To %s\n\n' % envelope.rcpttos)
            fp.write('%s\n' % description)

        with open('error/%s.txt' % now, 'ab') as fp:
            fp.write(envelope.message.as_bytes())
