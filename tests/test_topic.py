"""Chapter > Topics (/core/topic/list/<chapter id>)."""

from playwright.sync_api import expect

from pages.chapter_page import ChapterPage
from pages.topic_page import TopicPage
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

LEVEL = "topic"


# ---------- Navigation and API ----------


def test_topic_page_opens_from_chapter(admin_page, qa_tree):
    chapters = ChapterPage(admin_page)
    chapters.open(qa_tree["chapter"]["parent"])

    chapters.open_children(qa_tree["chapter"]["name"])

    check_opened_level(
        TopicPage(admin_page),
        qa_tree["topic"],
        [qa_tree["course_name"], qa_tree["subject"]["name"], qa_tree["chapter"]["name"]],
    )


def test_topic_api_children_match_ui(level_page, syllabus_api, qa_tree):
    check_api_children_match_ui(level_page, syllabus_api, qa_tree["topic"])


# ---------- CRUD ----------


def test_topic_create_popup_opens_and_closes(level_page):
    check_create_popup_opens_and_closes(level_page)


def test_topic_create_required_field_validation(level_page):
    check_create_required_field_validation(level_page)


def test_create_topic_appears_under_chapter(level_page, syllabus_api, qa_tree, level_item_name):
    check_create_appears_under_parent(level_page, syllabus_api, qa_tree["topic"], level_item_name)


def test_edit_topic(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_updates_details(level_page, syllabus_api, qa_tree["topic"], level_item_name)


def test_delete_topic(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_removes_record(level_page, syllabus_api, qa_tree["topic"], level_item_name)


# ---------- Availability ----------


def test_topic_cannot_be_available_without_available_subtopic(admin_page, syllabus_api, branch):
    topics = set_available(admin_page, branch["topic"], True)

    expect(topics.alert(TopicPage.NO_AVAILABLE_CHILD_MESSAGE)).to_be_visible()
    expect_available(admin_page, syllabus_api, branch["topic"], False)


# ---------- Page UI, navigation and empty state ----------


def test_topic_list_page_ui_elements(level_page, qa_tree):
    check_list_page_ui(level_page, qa_tree["topic"])


def test_topic_breadcrumb_goes_back(level_page, qa_tree):
    check_breadcrumb_goes_back(level_page, qa_tree, "topic")


def test_topic_empty_state(level_page, syllabus_api, empty_parent):
    check_empty_state(level_page, syllabus_api, "topic", empty_parent)


# ---------- Cancel actions ----------


def test_topic_edit_popup_close_discards_changes(level_page, syllabus_api, qa_tree):
    check_edit_close_discards_changes(level_page, syllabus_api, qa_tree["topic"])


def test_topic_delete_can_be_cancelled(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_can_be_cancelled(level_page, syllabus_api, qa_tree["topic"], level_item_name)


# ---------- Invalid input, boundaries and duplicates ----------


def test_topic_whitespace_only_title_is_rejected(level_page, syllabus_api, qa_tree):
    check_whitespace_title_is_rejected(level_page, syllabus_api, qa_tree["topic"])


def test_topic_title_at_max_length_is_saved(level_page, syllabus_api, qa_tree, level_item_name):
    check_max_length_title_is_saved(level_page, syllabus_api, qa_tree["topic"], level_item_name)


def test_topic_title_over_max_length_is_rejected_without_server_error(level_page, syllabus_api, qa_tree, level_item_name):
    check_over_max_length_title_is_rejected(level_page, syllabus_api, qa_tree["topic"], level_item_name)


def test_topic_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree["topic"], level_item_name)


def test_topic_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree["topic"], level_item_name)


# ---------- Persistence, Sort, Duplicate ----------


def test_topic_edit_persists(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_persists_and_is_logged(level_page, syllabus_api, qa_tree["topic"], level_item_name)


def test_topic_sort_reorders_items(level_page, syllabus_api, qa_tree, level_item_name):
    check_sort_reorders_items(level_page, syllabus_api, qa_tree["topic"], level_item_name)


def test_duplicate_topic_creates_copy(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_creates_copy(level_page, syllabus_api, qa_tree, qa_tree["topic"], level_item_name)


# ---------- Server errors ----------


def test_topic_unknown_id_has_no_server_error(syllabus_api):
    check_unknown_id_has_no_server_error(syllabus_api, "topic")
