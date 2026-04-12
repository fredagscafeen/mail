import requests

try:
    from datmail.config import DJANGO_API_URL, DJANGO_API_TOKEN
except ImportError:
    DJANGO_API_URL = None
    DJANGO_API_TOKEN = None

class DjangoAPIClient:
    def __init__(self):
        if not DJANGO_API_URL or not DJANGO_API_TOKEN:
            raise ValueError("DJANGO_API_URL and DJANGO_API_TOKEN must be set in config")
        self.base_url = DJANGO_API_URL.rstrip("/")
        self.token = DJANGO_API_TOKEN

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def upsert_incoming_mail(self, payload):
        r = requests.post(
            f"{self.base_url}/monitoring/incoming-mails/",
            json=payload,
            headers=self._headers(),
            timeout=5,
        )
        r.raise_for_status()

        return r

    def get_admin_emails(self):
        return self.get_mailinglist_members("admin")
    
    def get_mailinglist_members(self, list_name):
        r = requests.get(
            f"{self.base_url}/mail/lists/{list_name}/",
            headers=self._headers(),
            timeout=5
        )
        r.raise_for_status()
        result_json = r.json()

        members = result_json.get("members", [])
        if not isinstance(members, list):
            raise ValueError("Expected 'members' to be a list")
        
        email_list = [email for email in members if isinstance(email, str)]
        ids_list = [id for id in members if isinstance(id, int)]
        
        if len(email_list) != len(members):
            raise ValueError("Some emails in 'members' were not strings")
        if len(ids_list) != len(members):
            raise ValueError("Some ids in 'members' were not integers")

        if len(email_list) == 0:
            raise ValueError("Received empty list of emails")
        if len(ids_list) == 0:
            raise ValueError("Received empty list of ids")

        return email_list, ids_list

    def get_mailinglist_info(self, list_name):
        r = requests.get(
            f"{self.base_url}/mail/lists/{list_name}/",
            headers=self._headers(),
            timeout=5
        )
        r.raise_for_status()
        return r.json()
