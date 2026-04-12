import importlib
import sys
import types
import unittest
from unittest.mock import patch
import datmail


if "requests" not in sys.modules:
    requests = types.ModuleType("requests")

    def _unexpected_post(*args, **kwargs):
        raise AssertionError("requests.post should be patched in tests")

    requests.post = _unexpected_post
    sys.modules["requests"] = requests


config = types.ModuleType("datmail.config")
config.DJANGO_API_URL = "http://localhost:8000/en/api"
config.DJANGO_API_TOKEN = "secret-token"
sys.modules["datmail.config"] = config
datmail.config = config

from datmail.django_api_client import DjangoAPIClient

class DjangoAPIClientTests(unittest.TestCase):
    def setUp(self):
        self.api_client = DjangoAPIClient()

    def test_upsert_incoming_mail_posts_expected_payload(self):
        with patch("datmail.django_api_client.requests.post") as mocked_post:
            payload = {"request_uuid": "55555555-5555-4555-8555-555555555555"}
            self.api_client.upsert_incoming_mail(payload)

            mocked_post.assert_called_once_with(
                "http://localhost:8000/en/api/monitoring/incoming-mails/",
                json=payload,
                headers={
                    "Authorization": "Bearer secret-token",
                    "Content-Type": "application/json",
                },
                timeout=5,
            )
