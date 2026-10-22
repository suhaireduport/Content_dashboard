"""Page Object for Course > Subjects (/core/subject/list/<course id>)."""

from playwright.sync_api import Locator

from pages.syllabus_level_page import SyllabusLevelPage


class SubjectPage(SyllabusLevelPage):
    LEVEL = "Subject"
    PATH = "subject"
    CHILD_LINK = "Chapters"
    CREATE_REQUIRED_FIELDS = ("title", "short_title", "phone", "core_type", "asset")
    CREATE_HAS_AVAILABILITY = False
    MENU_ITEMS = ("Change Log", "Duplicate", "Edit", "Delete")

    def fill_required_create_fields(self) -> None:
        self.create_field("short_title").fill("QA")
        self.create_field("phone").fill("1234567890")
        self.create_field("core_type").select_option("CORE")
        self.create_field("asset").select_option(index=1)  # first real asset after the placeholder

    @property
    def create_cost_input(self) -> Locator:
        return self.create_field("cost")

    def is_create_cost_below_minimum(self) -> bool:
        return self.create_cost_input.evaluate("el => el.validity.rangeUnderflow")
