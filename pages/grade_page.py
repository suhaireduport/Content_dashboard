"""Page Objects for the Content Dashboard > Grade page and a grade's "Sort Courses" page."""

import re

from playwright.sync_api import Locator, Page

from config import BASE_URL
from pages.syllabus_item_page import SyllabusItemPage


class GradePage(SyllabusItemPage):
    ITEM = "Grade"
    PATH = "grade"

    def grade_id(self, name: str) -> str:
        return self.item_card(name).locator("[data-grade-id]").first.get_attribute("data-grade-id")

    def open_course_sort(self, name: str) -> None:
        """Click the grade card's "Sort Courses" (opens /core/course/sort/<grade id>)."""
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.item_card(name).get_by_role("button", name="Sort Courses").click()


class CourseSortPage:
    """Grade > "Sort Courses": drag & drop the grade's course cards, then "Save Changes"."""

    URL_PATTERN = re.compile(r"/core/course/sort/\d+$")
    SORTED_MESSAGE = "Course Sorted successfully!"

    def __init__(self, page: Page):
        self.page = page
        self.heading = page.get_by_role("heading", name="COURSES", level=1)
        self.sort_area = page.locator("#sort-parent-div")
        self.cards = self.sort_area.locator(".sort-child")
        self.order_input = page.locator("#sort-order")
        self.save_button = page.get_by_role("button", name="Save Changes")
        self.success_alert = page.get_by_role("alert")

    def card(self, title: str) -> Locator:
        return self.cards.filter(has=self.page.locator("h3", has_text=re.compile(rf"^\s*{re.escape(title)}\s*$")))

    def card_titles(self) -> list[str]:
        return [t.strip() for t in self.cards.locator("h3").all_text_contents()]

    def card_ids(self) -> list[str]:
        return self.cards.evaluate_all("cards => cards.map(c => c.dataset.id)")

    def prev_order(self, title: str) -> str:
        """The "Prev order : N" badge of a card (the saved position)."""
        return self.card(title).locator(".badge.bg-primary").inner_text().strip()

    # ---------- Actions ----------

    def open(self, grade_id: str) -> None:
        self.page.goto(f"{BASE_URL}/core/course/sort/{grade_id}", wait_until="domcontentloaded")

    def drag_onto(self, moving: str, target: str) -> None:
        """Drop `moving` onto `target` (the page inserts it before/after the target)."""
        self.card(moving).drag_to(self.card(target))

    def drag_into_gap_after(self, moving: str, index: int) -> None:
        """Drop `moving` into the gap between the cards at positions `index` and `index + 1`."""
        left = self.cards.nth(index).locator(".card").bounding_box()
        right = self.cards.nth(index + 1).locator(".card").bounding_box()
        area = self.sort_area.bounding_box()
        gap_x = (left["x"] + left["width"] + right["x"]) / 2
        gap_y = left["y"] + left["height"] / 2
        self.card(moving).drag_to(
            self.sort_area, target_position={"x": gap_x - area["x"], "y": gap_y - area["y"]}
        )

    def save_changes(self) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.save_button.click()
