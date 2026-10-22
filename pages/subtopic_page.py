"""Page Object for Topic > Subtopics (/core/subtopic/list/<topic id>)."""

from playwright.sync_api import Locator

from pages.syllabus_level_page import SyllabusLevelPage


class SubtopicPage(SyllabusLevelPage):
    LEVEL = "Subtopic"
    PATH = "subtopic"
    CHILD_LINK = None  # last level: content is mapped from the content pages
    CREATE_REQUIRED_FIELDS = ("title", "published_at")
    MENU_ITEMS = ("Videos", "Questions", "Change Log", "Duplicate", "Edit", "Delete")
    DEFAULT_THRESHOLD = "50"
    PUBLISHED_AT = "2026-01-01T00:00"
    PUBLISHED_AT_TEXT = "Published at: 2026-01-01 00:00:00"
    NO_CONTENT_MESSAGE = (
        "There is no content in this subtopic. Please map contents to it to make it available."
    )

    def fill_required_create_fields(self) -> None:
        self.create_field("published_at").fill(self.PUBLISHED_AT)

    def card_published_at(self, name: str) -> Locator:
        return self.card(name).locator(".text-muted", has_text="Published at:")

    @property
    def create_pretest_checkbox(self) -> Locator:
        return self.create_field("pretest")

    @property
    def create_threshold_input(self) -> Locator:
        return self.create_field("threshold")
