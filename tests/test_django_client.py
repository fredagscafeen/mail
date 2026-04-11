import importlib
import sys
import types
import unittest
from unittest.mock import patch


if "requests" not in sys.modules:
    requests = types.ModuleType("requests")

    def _unexpected_post(*args, **kwargs):
        raise AssertionError("requests.post should be patched in tests")

    requests.post = _unexpected_post
    sys.modules["requests"] = requests


class DjangoMonitoringClientTests(unittest.TestCase):
    def test_upsert_incoming_mail_posts_expected_payload(self):
        django_client = importlib.import_module("datmail.django_client")

        with patch("datmail.django_client.requests.post") as mocked_post:
            client = django_client.DjangoMonitoringClient(
                "https://web/api", "secret-token"
            )

            payload = {"request_uuid": "55555555-5555-4555-8555-555555555555"}
            client.upsert_incoming_mail(payload)

        mocked_post.assert_called_once_with(
            "https://web/api/monitoring/incoming-mails/",
            json=payload,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
