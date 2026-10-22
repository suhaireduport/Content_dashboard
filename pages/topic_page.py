"""Page Object for Chapter > Topics (/core/topic/list/<chapter id>)."""

from pages.syllabus_level_page import SyllabusLevelPage


class TopicPage(SyllabusLevelPage):
    LEVEL = "Topic"
    PATH = "topic"
    CHILD_LINK = "Subtopics"
    CREATE_REQUIRED_FIELDS = ("title", "core_type")
    MENU_ITEMS = ("Questions", "Duplicate", "Edit", "Delete")  # no Change Log at this level
    NO_AVAILABLE_CHILD_MESSAGE = (
        "There are no available subtopics or contents in this topic. Please ensure at least "
        "one subtopic or content is available to make this topic available."
    )

    def fill_required_create_fields(self) -> None:
        self.create_field("core_type").select_option("CORE")
