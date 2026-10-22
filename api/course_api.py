"""HTTP client for the Course endpoints used by the Course page.

The app has no JSON API for courses: the page is server-rendered and only calls
  GET /core/course/list              -> full list as HTML
  GET /core/course/update/<id>       -> Edit form as an HTML fragment (loaded on "Edit")
This client calls those same endpoints with Playwright's APIRequestContext and parses
the returned HTML with Python's built-in parser.
"""

import re
from html.parser import HTMLParser

from playwright.sync_api import APIRequestContext, APIResponse

from config import BASE_URL


class CourseApi:
    LIST_URL = f"{BASE_URL}/core/course/list"
    LOGIN_REDIRECT_PREFIX = "/staff-dashboard/login/"

    def __init__(self, request: APIRequestContext):
        self.request = request

    # ---------- Raw endpoint calls ----------

    def get_list(self, follow_redirects: bool = True) -> APIResponse:
        return self.request.get(self.LIST_URL, max_redirects=20 if follow_redirects else 0)

    def get_edit_form(self, course_id: str) -> APIResponse:
        return self.request.get(f"{BASE_URL}/core/course/update/{course_id}")

    # ---------- Parsed data ----------

    ARCHIVED_CARDS_URL = f"{BASE_URL}/core/get/course-cards"
    MENTOR_LIST_URL = f"{BASE_URL}/core/get/mentor-list"

    def get_archived_cards(self) -> APIResponse:
        """Archived course cards (HTML) that the page lazy-loads on the first Archived/All visit."""
        return self.request.get(self.ARCHIVED_CARDS_URL)

    def list_courses(self) -> list[dict]:
        """Every course: [{"id", "title", "active"}, ...]. Combines the list page with the
        lazily loaded archived cards (where the channel has that endpoint)."""
        parser = _CourseListParser()
        parser.feed(self.get_list().text())
        archived = self.get_archived_cards()
        if archived.ok:
            parser.feed(archived.text())
        unique = {}
        for course in parser.courses:
            unique.setdefault(course["id"], course)
        return list(unique.values())

    def list_archived_card_courses(self) -> list[dict]:
        parser = _CourseListParser()
        parser.feed(self.get_archived_cards().text())
        return parser.courses

    def mentor_list(self) -> list[dict]:
        """[{"id", "name", "active_students_count"}, ...] from GET /core/get/mentor-list."""
        return self.request.get(self.MENTOR_LIST_URL).json()["mentors"]

    def find_courses(self, title: str) -> list[dict]:
        return [course for course in self.list_courses() if course["title"] == title]

    def course_sort_order(self, grade_id: str) -> list[str]:
        """Course ids in the saved order of a grade, as served by its Sort Courses page
        (GET /core/course/sort/<grade id>; there is no JSON endpoint for this)."""
        html = self.request.get(f"{BASE_URL}/core/course/sort/{grade_id}").text()
        return re.findall(r'class="[^"]*\bsort-child\b[^"]*"[^>]*data-id="(\d+)"', html)

    def mentor_pool_names(self, course_id: str) -> list[str]:
        """Mentor names linked to a course, from the Course Mentor Pool page
        (GET /staff-dashboard/course_mentor_pool/)."""
        html = self.request.get(f"{BASE_URL}/staff-dashboard/course_mentor_pool/").text()
        row = re.search(rf"<tr>\s*<td>{course_id}</td>.*?</tr>", html, re.S)
        if not row:
            return []
        names = re.findall(r'class="card-body[^"]*">\s*(.*?)\s*<button', row.group(0), re.S)
        return [" ".join(name.replace("&nbsp;", " ").split()) for name in names]

    def edit_form_values(self, course_id: str) -> dict:
        """Values the server pre-fills in the Edit form: text/select labels and checkbox states."""
        parser = EditFormParser()
        parser.feed(self.get_edit_form(course_id).text())
        return parser.values


class _CourseListParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.courses = []
        self._current = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and "course-card" in (attrs.get("class") or "").split():
            self._current = {"id": None, "title": "", "active": attrs.get("data-active") == "true"}
            self.courses.append(self._current)
        elif self._current is not None:
            if tag == "h3" and not self._current["title"]:
                self._in_title = True
            if self._current["id"] is None and attrs.get("data-course-id"):
                self._current["id"] = attrs["data-course-id"]

    def handle_endtag(self, tag):
        if tag == "h3" and self._in_title:
            self._in_title = False
            self._current["title"] = self._current["title"].strip()

    def handle_data(self, data):
        if self._in_title:
            self._current["title"] += data


class EditFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}
        self._select = None
        self._option = None  # [is_selected, text]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        name = attrs.get("name")
        if tag == "input" and name:
            if attrs.get("type") == "checkbox":
                self.values[name] = "checked" in attrs
            elif attrs.get("type") != "hidden":
                self.values[name] = attrs.get("value", "")
        elif tag == "select":
            self._select = name
        elif tag == "option" and self._select:
            self._option = ["selected" in attrs, ""]

    def handle_endtag(self, tag):
        if tag == "option" and self._option:
            if self._option[0]:
                self.values[self._select] = self._option[1].strip()
            self._option = None
        elif tag == "select":
            self._select = None

    def handle_data(self, data):
        if self._option:
            self._option[1] += data
