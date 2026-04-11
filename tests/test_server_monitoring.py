import datetime
import importlib
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = "/Users/mmos/Github/fredagscafeen/mail/.worktrees/mail-monitoring-mail"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def load_server_module():
    import datmail

    emailtunnel = types.ModuleType("emailtunnel")

    class SMTPForwarder:
        def __init__(self, *args, **kwargs):
            pass

        def handle_envelope(self, envelope, peer):
            self._super_handled = True
            if getattr(self, "_forward_recipients", None) is not None:
                self.forward(
                    envelope,
                    envelope.message,
                    self._forward_recipients,
                    envelope.mailfrom,
                )
            return "handled-by-super"

        def forward(self, original_envelope, message, recipients, sender):
            return None

    class InvalidRecipient(Exception):
        pass

    class Envelope:
        def __init__(self, message, mailfrom, rcpttos):
            self.message = message
            self.mailfrom = mailfrom
            self.rcpttos = rcpttos

    class Message:
        def __init__(self, message):
            self.message = message

    emailtunnel.SMTPForwarder = SMTPForwarder
    emailtunnel.InvalidRecipient = InvalidRecipient
    emailtunnel.Envelope = Envelope
    emailtunnel.Message = Message
    emailtunnel.logger = Mock()
    sys.modules["emailtunnel"] = emailtunnel

    config = types.ModuleType("datmail.config")
    config.SRS_SECRET = "secret"
    config.CC_MAILLISTS = False
    config.ADMINS = []
    config.DATABASE = "sqlite"
    config.HOSTNAME = "host"
    config.USERNAME = "user"
    config.PASSWORD = "pass"
    config.S3_ENDPOINT_URL = "http://localhost"
    config.S3_ACCESS_KEY_ID = "access"
    config.S3_SECRET_ACCESS_KEY = "secret"
    sys.modules["datmail.config"] = config
    datmail.config = config

    address = types.ModuleType("datmail.address")

    class GroupAlias:
        def __init__(self, name):
            self.name = name

        def __str__(self):
            return self.name

    address.GroupAlias = GroupAlias
    address.translate_recipient = lambda name, list_ids=True: ([], {})
    sys.modules["datmail.address"] = address
    datmail.address = address

    headers = types.ModuleType("datmail.headers")
    headers.get_extra_headers = lambda sender, list_name, is_group: []
    sys.modules["datmail.headers"] = headers
    datmail.headers = headers

    delivery_reports = types.ModuleType("datmail.delivery_reports")
    delivery_reports.parse_delivery_report = lambda message: None
    sys.modules["datmail.delivery_reports"] = delivery_reports

    dmarc = types.ModuleType("datmail.dmarc")
    dmarc.has_strict_dmarc_policy = lambda domain: False
    sys.modules["datmail.dmarc"] = dmarc

    storage = types.ModuleType("datmail.storage")

    class Storage:
        def __init__(self, *args, **kwargs):
            pass

        def upload_object(self, body, object_name):
            return None

    storage.Storage = Storage
    sys.modules["datmail.storage"] = storage

    database = types.ModuleType("datmail.database")

    class Database:
        def get_mailinglists(self):
            return []

        def get_mailinglist_members(self, list_id):
            return []

        def get_email_addresses(self, member_ids):
            return []

    database.Database = Database
    sys.modules["datmail.database"] = database

    django_client = types.ModuleType("datmail.django_client")

    class DjangoMonitoringClient:
        def __init__(self, *args, **kwargs):
            pass

        def upsert_incoming_mail(self, payload):
            return None

    django_client.DjangoMonitoringClient = DjangoMonitoringClient
    sys.modules["datmail.django_client"] = django_client

    if "datmail.server" in sys.modules:
        return importlib.reload(sys.modules["datmail.server"])
    return importlib.import_module("datmail.server")


class FakeMessage:
    def __init__(self):
        self.headers = {}
        self.subject = "Subject"
        self.message = {"DKIM-Signature": "signature"}

    def add_header(self, name, value):
        self.headers[name] = value

    def get_header(self, name, default=None):
        return self.headers.get(name, default)

    def get_unique_header(self, name):
        if name not in self.headers:
            raise KeyError(name)
        return self.headers[name]

    def header_items(self):
        return []

    def get_all_headers(self, name):
        return []

    def set_unique_header(self, name, value):
        self.headers[name] = value


class FakeEnvelope:
    def __init__(self, rcpttos=None, mailfrom="sender@example.com"):
        self.mailfrom = mailfrom
        self.rcpttos = ["best@fredagscafeen.dk"] if rcpttos is None else rcpttos
        self.message = FakeMessage()
        self.from_domain = "example.com"
        self.received_at = datetime.datetime(2026, 4, 11, 15, 0, tzinfo=datetime.timezone.utc)

    def recipients(self):
        return [(self.rcpttos[0], self.rcpttos[0], "To")]


class ServerMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.server_module = load_server_module()
        self.forwarder = object.__new__(self.server_module.DatForwarder)
        self.forwarder.DOMAIN = "fredagscafeen.dk"
        self.forwarder.REWRITE_FROM = True
        self.forwarder.STRIP_HTML = False
        self.forwarder.monitoring_client = Mock()
        self.forwarder.store_failed_envelope = Mock()
        self.forwarder.fix_headers = Mock()
        self.forwarder.handle_delivery_report = Mock(return_value=False)
        self.forwarder.is_sender_authorized_for_list = Mock(return_value=True)
        self.forwarder.extract_original_sender = Mock(return_value="sender@example.com")
        self.forwarder.get_from_domain = Mock(return_value="example.com")
        self.forwarder.reject = Mock(return_value=None)
        self.forwarder.get_dsn_redirect_recipient = Mock(return_value=None)
        self.forwarder.storage = Mock()
        self.forwarder.deliver_recipients = {}
        self.forwarder.delivered = 0
        self.forwarder.year = 2026
        self.forwarder._super_handled = False
        self.forwarder._forward_recipients = None

    def test_log_receipt_stores_message_without_reporting_outcome(self):
        envelope = FakeEnvelope()

        self.forwarder.generate_uuid = Mock(return_value="request-123")
        self.forwarder.store_envelope = Mock()

        self.forwarder.log_receipt(peer=("127.0.0.1", 12345), envelope=envelope)

        self.forwarder.store_envelope.assert_called_once_with(envelope)
        self.forwarder.monitoring_client.upsert_incoming_mail.assert_not_called()

    def test_report_processed_mail_posts_expected_payload(self):
        envelope = FakeEnvelope()
        envelope.message.add_header("X-Fredagscafeen-Envelope-ID", "request-123")

        self.forwarder.report_processed_mail(
            envelope,
            expanded_recipients={"bob@example.com", "alice@example.com"},
            mailing_list_name="best",
        )

        self.forwarder.monitoring_client.upsert_incoming_mail.assert_called_once_with(
            {
                "request_uuid": "request-123",
                "received_at": "2026-04-11T15:00:00Z",
                "sender": "sender@example.com",
                "target": "best@fredagscafeen.dk",
                "mailing_list": "best",
                "status": "PROCESSED",
                "reason": "",
                "s3_object_key": "archive/request-123.eml",
                "expanded_recipients": ["alice@example.com", "bob@example.com"],
            }
        )

    def test_report_dropped_mail_posts_reason_without_expanded_recipients(self):
        envelope = FakeEnvelope()
        envelope.message.add_header("X-Fredagscafeen-Envelope-ID", "request-123")

        self.forwarder.report_dropped_mail(envelope, "spam filter triggered")

        self.forwarder.monitoring_client.upsert_incoming_mail.assert_called_once_with(
            {
                "request_uuid": "request-123",
                "received_at": "2026-04-11T15:00:00Z",
                "sender": "sender@example.com",
                "target": "best@fredagscafeen.dk",
                "mailing_list": None,
                "status": "DROPPED",
                "reason": "spam filter triggered",
                "s3_object_key": "archive/request-123.eml",
                "expanded_recipients": [],
            }
        )

    def test_report_dropped_mail_handles_missing_target(self):
        envelope = FakeEnvelope(rcpttos=[])
        envelope.message.add_header("X-Fredagscafeen-Envelope-ID", "request-123")

        self.forwarder.report_dropped_mail(envelope, "spam filter triggered")

        self.forwarder.monitoring_client.upsert_incoming_mail.assert_called_once_with(
            {
                "request_uuid": "request-123",
                "received_at": "2026-04-11T15:00:00Z",
                "sender": "sender@example.com",
                "target": "",
                "mailing_list": None,
                "status": "DROPPED",
                "reason": "spam filter triggered",
                "s3_object_key": "archive/request-123.eml",
                "expanded_recipients": [],
            }
        )

    def test_handle_envelope_reports_dropped_mail_after_reject(self):
        envelope = FakeEnvelope()

        self.forwarder.reject.return_value = "invalid header encoding"
        self.forwarder.report_dropped_mail = Mock()

        self.forwarder.handle_envelope(envelope, peer=("127.0.0.1", 12345))

        self.forwarder.store_failed_envelope.assert_called_once()
        self.forwarder.report_dropped_mail.assert_called_once_with(
            envelope,
            "Rejected by DatForwarder.reject (invalid header encoding)",
        )

    def test_handle_envelope_reports_processed_mail_after_super_handles_it(self):
        envelope = FakeEnvelope()
        envelope.message.add_header("X-Fredagscafeen-Envelope-ID", "request-123")
        envelope.received_at = datetime.datetime(
            2026, 4, 11, 15, 0, tzinfo=datetime.timezone.utc
        )

        self.forwarder._forward_recipients = ["alice@example.com", "bob@example.com"]
        self.forwarder.translate_recipient = Mock(
            side_effect=AssertionError("handle_envelope should not re-translate recipients for monitoring")
        )
        self.forwarder.report_processed_mail = Mock()

        result = self.forwarder.handle_envelope(envelope, peer=("127.0.0.1", 12345))

        self.assertEqual(result, "handled-by-super")
        self.forwarder.report_processed_mail.assert_called_once_with(
            envelope,
            {"alice@example.com", "bob@example.com"},
            "best",
        )

    def test_handle_envelope_reports_processed_mail_without_monitoring_translation(self):
        envelope = FakeEnvelope()
        envelope.message.add_header("X-Fredagscafeen-Envelope-ID", "request-123")
        self.forwarder._forward_recipients = ["alice@example.com"]
        self.forwarder.translate_recipient = Mock(
            side_effect=AssertionError("monitoring should use actual forwarded recipients")
        )
        self.forwarder.report_processed_mail = Mock()

        result = self.forwarder.handle_envelope(envelope, peer=("127.0.0.1", 12345))

        self.assertEqual(result, "handled-by-super")
        self.forwarder.report_processed_mail.assert_called_once_with(
            envelope,
            {"alice@example.com"},
            "best",
        )


if __name__ == "__main__":
    unittest.main()
