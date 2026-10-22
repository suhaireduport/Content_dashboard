"""Page Object for the Staff Dashboard home page (shown after a successful login)."""

import re

from playwright.sync_api import Page

from config import BASE_URL


class StaffDashboardPage:
    URL_PATTERN = re.compile(r"/staff-dashboard/$")
    PAGE_TITLE = "Home - Eduport Dashboard"

    def __init__(self, page: Page):
        self.page = page

        self.heading = page.get_by_role("heading", name="Admin Panel", level=1)
        self.go_to_content_dashboard_link = page.get_by_role(
            "link", name="Go To Content Dashboard"
        )

    # ---------- Actions ----------

    def go_to_content_dashboard(self) -> None:
        self.go_to_content_dashboard_link.click()


class MentorPoolPage:
    """Staff Dashboard > Mentor Management > Course Mentor Pool: one row per course with its mentors."""

    URL = f"{BASE_URL}/staff-dashboard/course_mentor_pool/"

    def __init__(self, page: Page):
        self.page = page
        self.heading = page.get_by_text("Course Mentor Pool", exact=True).first

    def open(self) -> None:
        self.page.goto(self.URL, wait_until="domcontentloaded")

    def course_row(self, course_id: str):
        return self.page.locator("tr").filter(has=self.page.locator("td", has_text=re.compile(rf"^\s*{course_id}\s*$")))

    def mentor_names(self, course_id: str) -> list[str]:
        texts = self.course_row(course_id).locator(".card-body").all_text_contents()
        return [re.sub(r"[^\w\s.-]+$", "", " ".join(text.split())).strip() for text in texts]
