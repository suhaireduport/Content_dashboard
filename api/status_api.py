"""HTTP client for the Status endpoints used by the Status page (/content/status/list).

Endpoints, as called by the page's own script (all need the X-Requested-With header):
  GET  /content/status/list?q=&type=&state=&course=  -> list fragment (HTML cards, data-post=<id>;
                                                         #st-results-meta data-count = total matches)
  GET  /content/status/detail/<id>                   -> {"id", "post_type", "title", "caption",
                                                         "video_url", "state", "publish_at",
                                                         "is_available", "images", "placements":
                                                         [{"course", "course_title", "link",
                                                         "batches"}], ...}
  GET  /content/status/course-search?q=<text>        -> {"courses": [{"value", "label", "hint"}]}
  GET  /content/status/link-options?course=<id>      -> {"options": [{"id", "label", "level", "deep_link"}]}
  GET  /content/status/batches?course=<id>           -> {"batches": [{"id", "title"}]}
  POST /content/status/delete/<id>                   -> {"ok", "message"}
"""

import re

from playwright.sync_api import APIRequestContext

from config import BASE_URL


class StatusApi:
    LIST_URL = f"{BASE_URL}/content/status/list"
    HEADERS = {"X-Requested-With": "XMLHttpRequest"}
    TIMEOUT = 60_000  # the dev server can take >30s to answer

    def __init__(self, request: APIRequestContext):
        self.request = request

    def _get_json(self, path: str, params: dict | None = None) -> dict:
        return self.request.get(
            f"{BASE_URL}{path}", params=params, headers=self.HEADERS, timeout=self.TIMEOUT
        ).json()

    def detail(self, status_id: str) -> dict:
        return self._get_json(f"/content/status/detail/{status_id}")

    def ids_matching(self, text: str) -> list[str]:
        """Ids of every status whose title, caption or course matches `text`, newest first
        (live, disabled and expired)."""
        fragment = self.request.get(
            self.LIST_URL, params={"q": text}, headers=self.HEADERS, timeout=self.TIMEOUT
        ).text()
        return list(dict.fromkeys(re.findall(r'data-post="(\d+)"', fragment)))

    def count(self, **filters: str) -> int:
        """Number of statuses matching the Status list filters (all pages), from the list
        fragment's data-count. Filters: q, type ("1"-"3"), state (live, scheduled, disabled,
        expired), course (id)."""
        fragment = self.request.get(
            self.LIST_URL, params=filters, headers=self.HEADERS, timeout=self.TIMEOUT
        ).text()
        return int(re.search(r'id="st-results-meta" data-count="(\d+)"', fragment).group(1))

    def course_hint(self, course_name: str) -> str:
        """Live count shown next to the course in the Course picker, e.g. "3/3 live"."""
        courses = self._get_json("/content/status/course-search", {"q": course_name})["courses"]
        return next(course["hint"] for course in courses if course["label"] == course_name)

    def link_options(self, course_id: str) -> list[dict]:
        return self._get_json("/content/status/link-options", {"course": str(course_id)})["options"]

    def batches(self, course_id: str) -> list[dict]:
        return self._get_json("/content/status/batches", {"course": str(course_id)})["batches"]

    def delete(self, status_id: str) -> None:
        # Django's CSRF check needs the page's token and, over HTTPS, a same-origin Referer
        token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            self.request.get(self.LIST_URL, timeout=self.TIMEOUT).text(),
        ).group(1)
        self.request.post(
            f"{BASE_URL}/content/status/delete/{status_id}",
            multipart={"csrfmiddlewaretoken": token},
            headers={**self.HEADERS, "Referer": self.LIST_URL},
            timeout=self.TIMEOUT,
        )

    def delete_matching(self, text: str) -> None:
        """Clean-up helper: delete every status that matches `text` (used with test course names)."""
        for status_id in self.ids_matching(text):
            self.delete(status_id)
