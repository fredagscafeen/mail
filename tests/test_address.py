import datetime
import importlib
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch
import requests_mock

import datmail


config = types.ModuleType("datmail.config")
config.DJANGO_API_URL = "http://localhost:8000/en/api"
config.DJANGO_API_TOKEN = "secret-token"
config.ADMINS = [("Admin1", "admin1@example.com"), ("Admin2", "admin2@example.com")]
sys.modules["datmail.config"] = config
datmail.config = config

import datmail.address as address
from datmail.django_api_client import DjangoAPIClient

class AddressTests(unittest.TestCase):
    def setUp(self):
        self.api_client = DjangoAPIClient()

    @requests_mock.Mocker()
    def test_get_admin_emails(self, m):
        m.get("http://localhost:8000/en/api/mail/lists/admin/", json={
            "id": 69,
            "name": "admin",
            "isOnlyInternal": False,
            "members": [
                {
                    "id": 1,
                    "name": "Test User",
                    "email": "test@example.com"
                },
                {
                    "id": 2,
                    "name": "Test User 2",
                    "email": "test2@example.com"
                }
            ]
        })

        admin_emails, _ = address.get_admin_emails()

        self.assertEqual(admin_emails, ["test@example.com", "test2@example.com"])
    
    def test_get_admin_emails_fallback(self):
        self.api_client.get_admin_emails = Mock(side_effect=Exception("API error"))

        admin_emails, _ = address.get_admin_emails()

        self.assertEqual(admin_emails, ["admin1@example.com", "admin2@example.com"])
    
    def test_get_admin_emails_empty_api_response(self):
        self.api_client.get_admin_emails = Mock(return_value=[])

        admin_emails, _ = address.get_admin_emails()

        self.assertEqual(admin_emails, ["admin1@example.com", "admin2@example.com"])

    @requests_mock.Mocker()
    def test_parse_alias_group(self, m):
        m.get("http://localhost:8000/en/api/mail/lists/testlist/", json={
            "id": 42,
            "name": "testlist",
            "isOnlyInternal": False,
            "members": [
                {
                    "id": 1,
                    "name": "Test User",
                    "email": "test@example.com"
                },
                {
                    "id": 2,
                    "name": "Test User 2",
                    "email": "test2@example.com"
                }
            ]
        })

        email_list, group_alias, id, is_only_internal = address.parse_alias_group(
            "testlist", self.api_client
        )

        self.assertEqual(email_list, ["test@example.com", "test2@example.com"])
        self.assertEqual(group_alias, address.GroupAlias("testlist"))
        self.assertEqual(id, 42)
        self.assertFalse(is_only_internal)

    @requests_mock.Mocker()
    def test_parse_alias_group_not_found(self, m):
        m.get("http://localhost:8000/en/api/mail/lists/nonexistent/", status_code=404)

        result = address.parse_alias_group("nonexistent", self.api_client)
        self.assertEqual(result, (None, None, None, None))

    @requests_mock.Mocker()
    def test_parse_alias_group_empty(self, m):
        m.get("http://localhost:8000/en/api/mail/lists/emptylist/", json={
            "id": 43,
            "name": "emptylist",
            "isOnlyInternal": False,
            "members": []
        })

        email_list, group_alias, id, is_only_internal = address.parse_alias_group(
            "emptylist", self.api_client
        )

        self.assertEqual(email_list, None)
        self.assertEqual(group_alias, None)
        self.assertEqual(id, None)
        self.assertEqual(is_only_internal, None)
    
    def test_translate_recipient_invalid_alias(self):
        self.api_client.get_mailinglist_info = Mock(return_value=None)

        with self.assertRaises(address.InvalidRecipient):
            address.translate_recipient("invalidalias", list_group_origins=True)
    
    def test_translate_recipient_api_error(self):
        self.api_client.get_mailinglist_info = Mock(side_effect=Exception("API error"))

        with self.assertRaises(address.InvalidRecipient):
            address.translate_recipient("anyalias", list_group_origins=True)
    
    @requests_mock.Mocker()
    def test_translate_recipient_valid_alias(self, m):
        m.get("http://localhost:8000/en/api/mail/lists/testlist/", json={
            "id": 42,
            "name": "testlist",
            "isOnlyInternal": False,
            "members": [
                {
                    "id": 1,
                    "name": "Test User",
                    "email": "test@example.com"
                },
                {
                    "id": 2,
                    "name": "Test User 2",
                    "email": "test2@example.com"
                }
            ]
        })

        recipient_emails, group_origins = address.translate_recipient("testlist", list_group_origins=True)

        self.assertIn("test@example.com", recipient_emails)
        self.assertIn("test2@example.com", recipient_emails)
        self.assertEqual(group_origins.get("test@example.com"), address.GroupAlias("testlist"))
        self.assertEqual(group_origins.get("test2@example.com"), address.GroupAlias("testlist"))