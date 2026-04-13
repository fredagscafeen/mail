import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

import datmail.control
from datmail.control import create_control_server


class ControlServerTests(unittest.TestCase):
    def start_server(self, forwarder=None):
        if forwarder is None:
            forwarder = Mock()
        server = create_control_server(
            forwarder,
            token="shared-secret",
            host="127.0.0.1",
            port=0,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        return server, forwarder

    def post(self, server, payload, token="shared-secret"):
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/control/resend",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return urllib.request.urlopen(request)

    def test_resend_endpoint_authenticates_and_dispatches_resend(self):
        server, forwarder = self.start_server()

        response = self.post(
            server,
            {
                "request_uuid": "request-123",
                "target": "alice@example.com",
                "sender": "sender@example.com",
                "original_target": "best@fredagscafeen.dk",
            },
        )

        self.assertEqual(response.status, 202)
        self.assertEqual(json.loads(response.read()), {"status": "queued"})
        forwarder.resend_archived_mail.assert_called_once_with(
            request_uuid="request-123",
            target="alice@example.com",
            sender="sender@example.com",
            original_target="best@fredagscafeen.dk",
        )

    def test_resend_endpoint_rejects_invalid_token(self):
        server, forwarder = self.start_server()

        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(
                server,
                {
                    "request_uuid": "request-123",
                    "target": "alice@example.com",
                    "sender": "sender@example.com",
                    "original_target": "best@fredagscafeen.dk",
                },
                token="wrong-token",
            )

        self.assertEqual(error.exception.code, 401)
        forwarder.resend_archived_mail.assert_not_called()

    def test_resend_endpoint_returns_server_error_when_resend_fails(self):
        server, forwarder = self.start_server()
        forwarder.resend_archived_mail.side_effect = RuntimeError("S3 unavailable")

        with patch.object(datmail.control, "logger") as logger:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post(
                    server,
                    {
                        "request_uuid": "request-123",
                        "target": "alice@example.com",
                        "sender": "sender@example.com",
                        "original_target": "best@fredagscafeen.dk",
                    },
                )

        self.assertEqual(error.exception.code, 502)
        logger.exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
