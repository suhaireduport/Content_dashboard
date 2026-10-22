"""Subject > Chapters (/core/chapter/list/<subject id>)."""

from playwright.sync_api import expect

from pages.chapter_page import ChapterPage
from pages.subject_page import SubjectPage
from tests.hierarchy_helpers import (
    check_api_children_match_ui,
    check_breadcrumb_goes_back,
    check_create_appears_under_parent,
    check_create_popup_opens_and_closes,
    check_create_required_field_validation,
    check_delete_can_be_cancelled,
    check_delete_removes_record,
    check_duplicate_creates_copy,
    check_duplicate_title_creates_separate_record,
    check_edit_close_discards_changes,
    check_edit_persists_and_is_logged,
    check_edit_updates_details,
    check_edit_with_empty_title_is_rejected,
    check_empty_state,
    check_list_page_ui,
    check_max_length_title_is_saved,
    check_opened_level,
    check_over_max_length_title_is_rejected,
    check_sort_reorders_items,
    check_unknown_id_has_no_server_error,
    check_whitespace_title_is_rejected,
    expect_available,
    set_available,
)

LEVEL = "chapter"


# ---------- Navigation and API ----------


def test_chapter_page_opens_from_subject(admin_page, qa_tree):
    subjects = SubjectPage(admin_page)
    subjects.open(qa_tree["subject"]["parent"])

    subjects.open_children(qa_tree["subject"]["name"])

    check_opened_level(ChapterPage(admin_page), qa_tree["chapter"], [qa_tree["course_name"], qa_tree["subject"]["name"]])


def test_chapter_api_children_match_ui(level_page, syllabus_api, qa_tree):
    check_api_children_match_ui(level_page, syllabus_api, qa_tree["chapter"])


# ---------- CRUD ----------


def test_chapter_create_popup_opens_and_closes(level_page):
    check_create_popup_opens_and_closes(level_page)


def test_chapter_create_required_field_validation(level_page):
    check_create_required_field_validation(level_page)


def test_create_chapter_appears_under_subject(level_page, syllabus_api, qa_tree, level_item_name):
    check_create_appears_under_parent(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


def test_edit_chapter(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_updates_details(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


def test_delete_chapter(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_removes_record(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


# ---------- Availability ----------


def test_chapter_cannot_be_available_without_available_topic(admin_page, syllabus_api, branch):
    set_available(admin_page, branch["chapter"], True)

    expect_available(admin_page, syllabus_api, branch["chapter"], False)


# ---------- Page UI, navigation and empty state ----------


def test_chapter_list_page_ui_elements(level_page, qa_tree):
    check_list_page_ui(level_page, qa_tree["chapter"])


def test_chapter_breadcrumb_goes_back(level_page, qa_tree):
    check_breadcrumb_goes_back(level_page, qa_tree, "chapter")


def test_chapter_empty_state(level_page, syllabus_api, empty_parent):
    check_empty_state(level_page, syllabus_api, "chapter", empty_parent)


# ---------- Cancel actions ----------


def test_chapter_edit_popup_close_discards_changes(level_page, syllabus_api, qa_tree):
    check_edit_close_discards_changes(level_page, syllabus_api, qa_tree["chapter"])


def test_chapter_delete_can_be_cancelled(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_can_be_cancelled(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


# ---------- Invalid input, boundaries and duplicates ----------


def test_chapter_whitespace_only_title_is_rejected(level_page, syllabus_api, qa_tree):
    check_whitespace_title_is_rejected(level_page, syllabus_api, qa_tree["chapter"])


def test_chapter_title_at_max_length_is_saved(level_page, syllabus_api, qa_tree, level_item_name):
    check_max_length_title_is_saved(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


def test_chapter_title_over_max_length_is_rejected_without_server_error(level_page, syllabus_api, qa_tree, level_item_name):
    check_over_max_length_title_is_rejected(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


def test_chapter_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


def test_chapter_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


# ---------- Persistence, Sort, Duplicate ----------


def test_chapter_edit_persists_and_is_logged(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_persists_and_is_logged(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


def test_chapter_sort_reorders_items(level_page, syllabus_api, qa_tree, level_item_name):
    check_sort_reorders_items(level_page, syllabus_api, qa_tree["chapter"], level_item_name)


def test_duplicate_chapter_creates_copy(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_creates_copy(level_page, syllabus_api, qa_tree, qa_tree["chapter"], level_item_name)


# ---------- Server errors ----------


def test_chapter_unknown_id_has_no_server_error(syllabus_api):
    check_unknown_id_has_no_server_error(syllabus_api, "chapter")


# ---------- Chapter fields ----------


def test_chapter_subscription_required_badge(level_page, level_item_name):
    level_page.create_chapter(f"{level_item_name} paid", subscription_required=True)
    level_page.create_chapter(f"{level_item_name} free", subscription_required=False)

    expect(level_page.card_subscription_badge(f"{level_item_name} paid")).to_have_text(ChapterPage.SUBSCRIPTION_REQUIRED)
    expect(level_page.card_subscription_badge(f"{level_item_name} free")).to_have_text(ChapterPage.SUBSCRIPTION_NOT_REQUIRED)
