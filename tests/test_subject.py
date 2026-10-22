"""Course > Subjects (/core/subject/list/<course id>)."""

from playwright.sync_api import expect

from api.syllabus_api import SyllabusApi
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

LEVEL = "subject"


# ---------- Navigation and API ----------


def test_subject_page_opens_from_course(course_page, qa_tree):
    course_page.open_subjects(qa_tree["course_name"])

    check_opened_level(SubjectPage(course_page.page), qa_tree["subject"], [qa_tree["course_name"]])


def test_subject_api_children_match_ui(level_page, syllabus_api, qa_tree):
    check_api_children_match_ui(level_page, syllabus_api, qa_tree["subject"])


def test_children_api_requires_login(browser, qa_tree):
    context = browser.new_context()
    try:
        response = context.request.get(
            SyllabusApi.CHILDREN_URL,
            params={"syllabus": qa_tree["course"], "type": "subject"},
            max_redirects=0,
        )
        assert response.status == 302
        assert response.headers["location"].startswith("/staff-dashboard/login/")
    finally:
        context.close()


# ---------- CRUD ----------


def test_subject_create_popup_opens_and_closes(level_page):
    check_create_popup_opens_and_closes(level_page)


def test_subject_create_required_field_validation(level_page):
    check_create_required_field_validation(level_page)


def test_create_subject_appears_under_course(level_page, syllabus_api, qa_tree, level_item_name):
    check_create_appears_under_parent(level_page, syllabus_api, qa_tree["subject"], level_item_name)


def test_edit_subject(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_updates_details(level_page, syllabus_api, qa_tree["subject"], level_item_name)


def test_delete_subject(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_removes_record(level_page, syllabus_api, qa_tree["subject"], level_item_name)


# ---------- Availability ----------


def test_subject_cannot_be_available_without_available_chapter(admin_page, syllabus_api, branch):
    set_available(admin_page, branch["subject"], True)

    expect_available(admin_page, syllabus_api, branch["subject"], False)


# ---------- Page UI, navigation and empty state ----------


def test_subject_list_page_ui_elements(level_page, qa_tree):
    check_list_page_ui(level_page, qa_tree["subject"])


def test_subject_breadcrumb_goes_back(level_page, qa_tree):
    check_breadcrumb_goes_back(level_page, qa_tree, "subject")


def test_subject_empty_state(level_page, syllabus_api, empty_parent):
    check_empty_state(level_page, syllabus_api, "subject", empty_parent)


# ---------- Cancel actions ----------


def test_subject_edit_popup_close_discards_changes(level_page, syllabus_api, qa_tree):
    check_edit_close_discards_changes(level_page, syllabus_api, qa_tree["subject"])


def test_subject_delete_can_be_cancelled(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_can_be_cancelled(level_page, syllabus_api, qa_tree["subject"], level_item_name)


# ---------- Invalid input, boundaries and duplicates ----------


def test_subject_whitespace_only_title_is_rejected(level_page, syllabus_api, qa_tree):
    check_whitespace_title_is_rejected(level_page, syllabus_api, qa_tree["subject"])


def test_subject_title_at_max_length_is_saved(level_page, syllabus_api, qa_tree, level_item_name):
    check_max_length_title_is_saved(level_page, syllabus_api, qa_tree["subject"], level_item_name)


def test_subject_title_over_max_length_is_rejected_without_server_error(level_page, syllabus_api, qa_tree, level_item_name):
    check_over_max_length_title_is_rejected(level_page, syllabus_api, qa_tree["subject"], level_item_name)


def test_subject_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree["subject"], level_item_name)


def test_subject_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree["subject"], level_item_name)


# ---------- Persistence, Sort, Duplicate ----------


def test_subject_edit_persists_and_is_logged(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_persists_and_is_logged(level_page, syllabus_api, qa_tree["subject"], level_item_name)


def test_subject_sort_reorders_items(level_page, syllabus_api, qa_tree, level_item_name):
    check_sort_reorders_items(level_page, syllabus_api, qa_tree["subject"], level_item_name)


def test_duplicate_subject_creates_copy(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_creates_copy(level_page, syllabus_api, qa_tree, qa_tree["subject"], level_item_name)


# ---------- Server errors ----------


def test_subject_unknown_id_has_no_server_error(syllabus_api):
    check_unknown_id_has_no_server_error(syllabus_api, "subject")


def test_children_api_handles_invalid_requests(syllabus_api, qa_tree):
    """The children endpoint answers bad input with HTTP 200, no children and a message."""
    unknown_parent = syllabus_api.get_children("99999999", "chapter")
    bad_type = syllabus_api.get_children(qa_tree["course"], "unknown")
    non_numeric = syllabus_api.get_children("abc", "chapter")

    for response in (unknown_parent, bad_type, non_numeric):
        assert response.status == 200
        assert response.json()["children"] == []
    assert unknown_parent.json()["message"] == "SyllabusStructure matching query does not exist."
    assert bad_type.json()["message"] == "Invalid Syllabus Type"
    assert non_numeric.json()["message"]


# ---------- Subject fields ----------


def test_subject_cost_cannot_be_negative(level_page, level_item_name):
    cards_before = level_page.cards.count()
    level_page.open_add_popup()
    level_page.create_title_input.fill(level_item_name)
    level_page.fill_required_create_fields()
    level_page.create_cost_input.fill("-5")

    level_page.save_new_item()

    assert level_page.is_create_cost_below_minimum()
    expect(level_page.create_dialog).to_be_visible()
    expect(level_page.cards).to_have_count(cards_before)
