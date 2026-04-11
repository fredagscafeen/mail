import requests


class DjangoMonitoringClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.token = token

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
            timeout=10,
        )
        r.raise_for_status()
        
        return r
