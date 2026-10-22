"""Page Object for the Content Dashboard > Stream page."""

from pages.syllabus_item_page import SyllabusItemPage


class StreamPage(SyllabusItemPage):
    ITEM = "Stream"
    PATH = "stream"
