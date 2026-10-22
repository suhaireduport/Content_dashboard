"""Page Object for the Content Dashboard landing page (Board list)."""

import re

from playwright.sync_api import Locator, Page


class ContentDashboardPage:
    URL_PATTERN = re.compile(r"/core/board/list$")
    PAGE_TITLE = "Dashboard | Eduport"

    # Sidebar menu, grouped by section title, in the order shown on the page
    MENU_SECTIONS = {
        "Syllabus": ["Board", "Grade", "Medium", "Stream", "Course", "Batch", "Discount"],
        "Content": [
            "Exams", "Exam Question Set", "Question Set", "Files", "Videos", "Banner",
            "Report Questions", "Question Review", "Content Overview", "Faculty Review",
            "Bulk Upload Task", "Stickers",
        ],
        "Schedule": ["Zoom Meets", "Youtube live", "Notice", "Study Type"],
    }
    TOP_MENU_ITEMS = ["Dashboard v2"]

    def __init__(self, page: Page):
        self.page = page

        self.heading = page.get_by_role("heading", name="BOARD", level=1)
        self.sidebar_menu = page.locator("#navbar-nav")

    def menu_link(self, name: str) -> Locator:
        # Link names start with an icon glyph, and some names contain others
        # ("Board" is inside "Dashboard v2"), so match the whole name after the icon.
        return self.sidebar_menu.get_by_role(
            "link", name=re.compile(rf"^\W*{re.escape(name)}$")
        )

    def menu_section_title(self, title: str) -> Locator:
        return self.sidebar_menu.locator("li.menu-title", has_text=title)

    # ---------- Actions ----------

    def open_menu_item(self, name: str) -> None:
        # Some menu links reload the current URL (e.g. Board), so wait for the navigation
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.menu_link(name).click()
