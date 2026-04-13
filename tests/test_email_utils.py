import unittest
import datmail
import datmail.email_utils as email_utils

class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        datmail.config.DSN_RECIPIENT = "web@fredagscafeen.dk"

    def test_extract_original_sender_valid_input(self):
        cleaned_mail = email_utils.extract_original_sender("SRS0=HASH=TTL=orig-domain=orig-local@forwarder")
        self.assertEqual(cleaned_mail, "orig-local@orig-domain")

    def test_extract_original_sender_with_angle_brackets(self):
        cleaned_mail = email_utils.extract_original_sender("<SRS0=HASH=TTL=orig-domain=orig-local@forwarder>")
        self.assertEqual(cleaned_mail, "orig-local@orig-domain")

    def test_extract_original_sender_non_srs_input(self):
        cleaned_mail = email_utils.extract_original_sender("user@example.com")
        self.assertEqual(cleaned_mail, "user@example.com")

    def test_extract_original_sender_invalid_input(self):
        cleaned_mail = email_utils.extract_original_sender(12345)  # Not a string
        self.assertEqual(cleaned_mail, 12345)

    def test_get_dsn_redirect_recipient_report(self):
        class MockMessage:
            def get_unique_header(self, header_name):
                if header_name == "Content-Type":
                    return "multipart/report; report-type=delivery-status"
                raise KeyError

        class MockEnvelope:
            mailfrom = "<>"
            message = MockMessage()

        recipient = email_utils.get_dsn_redirect_recipient(MockEnvelope())
        self.assertEqual(recipient, "web@fredagscafeen.dk")

    def test_get_dsn_redirect_recipient_subject(self):
        class MockMessage:
            def get_unique_header(self, header_name):
                raise KeyError

            @property
            def subject(self):
                return "Undelivered Mail Returned to Sender"

        class MockEnvelope:
            mailfrom = "<>"
            message = MockMessage()

        recipient = email_utils.get_dsn_redirect_recipient(MockEnvelope())
        self.assertEqual(recipient, "web@fredagscafeen.dk")

    def test_get_dsn_redirect_recipient_no_match(self):
        class MockMessage:
            def get_unique_header(self, header_name):
                raise KeyError

            @property
            def subject(self):
                return "Some other subject"

        class MockEnvelope:
            mailfrom = ""
            message = MockMessage()

        recipient = email_utils.get_dsn_redirect_recipient(MockEnvelope())
        self.assertEqual(recipient, None)