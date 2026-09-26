from __future__ import annotations
import os, urllib.parse
from security.policy_engine import policy
from .http import request
from .base import IntegrationResult

class GoogleWorkspace:
    def __init__(self, token=None):
        self.token = token or os.getenv("GOOGLE_ACCESS_TOKEN", "")

    def ready(self):
        return bool(self.token)

    def _call(self, method, url, payload=None, write=False):
        if not self.token:
            return IntegrationResult(False, error="Google OAuth token required")
        if write and not policy.check("network.change", {"service": "google", "url": url}).allowed:
            return IntegrationResult(False, error="authorization required", environment_ready=True)
        return request(method, url, {"Authorization": "Bearer " + self.token}, payload)

    def gmail_search(self, q, max_results=20):
        query = urllib.parse.urlencode({"q": q, "maxResults": max_results})
        return self._call("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages?" + query)

    def gmail_get(self, message_id):
        return self._call("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}")

    def gmail_send(self, raw):
        return self._call("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {"raw": raw}, True)

    def calendar_events(self, calendar="primary"):
        cal = urllib.parse.quote(calendar, safe="")
        return self._call("GET", f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events")

    def calendar_create(self, event, calendar="primary"):
        cal = urllib.parse.quote(calendar, safe="")
        return self._call("POST", f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events", event, True)

    def calendar_update(self, event_id, event, calendar="primary"):
        cal = urllib.parse.quote(calendar, safe="")
        return self._call("PATCH", f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events/{event_id}", event, True)

    def calendar_delete(self, event_id, calendar="primary"):
        cal = urllib.parse.quote(calendar, safe="")
        return self._call("DELETE", f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events/{event_id}", write=True)

    def drive_search(self, q):
        query = urllib.parse.urlencode({"q": q, "fields": "files(id,name,mimeType,modifiedTime)"})
        return self._call("GET", "https://www.googleapis.com/drive/v3/files?" + query)

    def drive_get(self, file_id):
        return self._call("GET", f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media")

google_workspace = GoogleWorkspace()
