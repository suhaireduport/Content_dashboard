"""Page Object for the Content Dashboard > Medium page."""

from pages.syllabus_item_page import SyllabusItemPage


class MediumPage(SyllabusItemPage):
    ITEM = "Medium"
    PATH = "medium"
