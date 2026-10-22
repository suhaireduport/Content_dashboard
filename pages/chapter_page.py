"""Page Object for Subject > Chapters (/core/chapter/list/<subject id>)."""

from playwright.sync_api import Locator

from pages.syllabus_level_page import SyllabusLevelPage


class ChapterPage(SyllabusLevelPage):
    LEVEL = "Chapter"
    PATH = "chapter"
    CHILD_LINK = "Topics"
    CREATE_REQUIRED_FIELDS = ("title", "core_type", "faculty")
    MENU_ITEMS = ("Files", "Quizzes", "Change Log", "Duplicate", "Edit", "Delete")
    SUBSCRIPTION_REQUIRED = "Subscription Required"
    SUBSCRIPTION_NOT_REQUIRED = "Subscription Not Required"

    def fill_required_create_fields(self) -> None:
        self.create_field("core_type").select_option("CORE")
        self.create_field("faculty").select_option(label="00-Unassigned")

    def card_subscription_badge(self, name: str) -> Locator:
        # Second badge: "Subscription Required" / "Subscription Not Required"
        return self.card(name).locator(".badge").nth(1)

    def create_chapter(self, name: str, subscription_required: bool) -> None:
        self.open_add_popup()
        self.create_title_input.fill(name)
        self.fill_required_create_fields()
        self.create_field("subscription_required").set_checked(subscription_required)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.save_new_item()
