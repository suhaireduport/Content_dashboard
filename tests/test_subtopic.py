"""Topic > Subtopics (/core/subtopic/list/<topic id>), plus the availability rules that
start from subtopic content and run up the Topic > Chapter > Subject chain.

Observed availability behaviour (see report):
- Availability is set by hand in each level's Edit popup.
- A subtopic can be made Available only when it has mapped content; a parent only when
  it has an Available child. Otherwise the app refuses and shows a message.
- Parents are NOT switched on automatically when a child becomes Available.
- Removing the last content switches the whole chain to Not Available automatically.
"""

from playwright.sync_api import expect

from pages.course_page import CoursePage
from pages.subtopic_page import SubtopicPage
from pages.topic_page import TopicPage
from tests.hierarchy_helpers import (
    LEVEL_PAGES,
    PARENTS_BOTTOM_UP,
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
    map_video,
    set_available,
    unmap_videos,
)

LEVEL = "subtopic"


# ---------- Navigation and API ----------


def test_subtopic_page_opens_from_topic(admin_page, qa_tree):
    topics = TopicPage(admin_page)
    topics.open(qa_tree["topic"]["parent"])

    topics.open_children(qa_tree["topic"]["name"])

    check_opened_level(SubtopicPage(admin_page), qa_tree["subtopic"], [qa_tree["topic"]["name"]])


def test_navigation_from_course_to_subtopic(course_page: CoursePage, qa_tree):
    """Course page > Subject > Chapter > Topic > Subtopic, through the UI links."""
    course_page.open_subjects(qa_tree["course_name"])

    parent_names = [qa_tree["course_name"]]
    for level in ("subject", "chapter", "topic", "subtopic"):
        level_page = LEVEL_PAGES[level](course_page.page)
        check_opened_level(level_page, qa_tree[level], parent_names)
        if level_page.CHILD_LINK:
            level_page.open_children(qa_tree[level]["name"])
            parent_names.append(qa_tree[level]["name"])


def test_subtopic_api_children_match_ui(level_page, syllabus_api, qa_tree):
    check_api_children_match_ui(level_page, syllabus_api, qa_tree["subtopic"])


# ---------- CRUD ----------


def test_subtopic_create_popup_opens_and_closes(level_page):
    check_create_popup_opens_and_closes(level_page)


def test_subtopic_create_required_field_validation(level_page):
    check_create_required_field_validation(level_page)


def test_create_subtopic_appears_under_topic(level_page, syllabus_api, qa_tree, level_item_name):
    check_create_appears_under_parent(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)

    expect(level_page.card_published_at(level_item_name)).to_have_text(SubtopicPage.PUBLISHED_AT_TEXT)


def test_edit_subtopic(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_updates_details(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)

    # Saving the Edit form keeps the original "Published At"
    expect(level_page.card_published_at(f"{level_item_name} Updated")).to_have_text(SubtopicPage.PUBLISHED_AT_TEXT)


def test_delete_subtopic(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_removes_record(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


# ---------- Availability ----------


def test_new_hierarchy_is_not_available(admin_page, syllabus_api, branch):
    """Scenario: no subtopic has content -> the whole chain is Not Available."""
    for key in ("subtopic_1", "subtopic_2", *PARENTS_BOTTOM_UP):
        expect_available(admin_page, syllabus_api, branch[key], False)


def test_subtopic_without_content_cannot_be_available(admin_page, syllabus_api, branch):
    subtopics = set_available(admin_page, branch["subtopic_1"], True)

    expect(subtopics.alert(SubtopicPage.NO_CONTENT_MESSAGE)).to_be_visible()
    expect_available(admin_page, syllabus_api, branch["subtopic_1"], False)


def test_one_subtopic_with_content(admin_page, syllabus_api, branch, video_id):
    """Scenario: only one subtopic has content -> only it and its parent chain can be Available."""
    map_video(admin_page, video_id, branch, "subtopic_1")

    set_available(admin_page, branch["subtopic_1"], True)
    subtopics = set_available(admin_page, branch["subtopic_2"], True)
    expect(subtopics.alert(SubtopicPage.NO_CONTENT_MESSAGE)).to_be_visible()
    for key in PARENTS_BOTTOM_UP:
        set_available(admin_page, branch[key], True)

    expect_available(admin_page, syllabus_api, branch["subtopic_1"], True)
    expect_available(admin_page, syllabus_api, branch["subtopic_2"], False)
    for key in PARENTS_BOTTOM_UP:
        expect_available(admin_page, syllabus_api, branch[key], True)


def test_all_subtopics_with_content(admin_page, syllabus_api, branch, video_id):
    """Scenario: every subtopic has content -> the whole chain can be Available."""
    map_video(admin_page, video_id, branch, "subtopic_1")
    map_video(admin_page, video_id, branch, "subtopic_2")

    for key in ("subtopic_1", "subtopic_2", *PARENTS_BOTTOM_UP):
        set_available(admin_page, branch[key], True)

    for key in ("subtopic_1", "subtopic_2", *PARENTS_BOTTOM_UP):
        expect_available(admin_page, syllabus_api, branch[key], True)


def test_parents_are_not_made_available_automatically(admin_page, syllabus_api, branch, video_id):
    """Making a subtopic Available does not make its parents Available by itself."""
    map_video(admin_page, video_id, branch, "subtopic_1")

    set_available(admin_page, branch["subtopic_1"], True)

    expect_available(admin_page, syllabus_api, branch["subtopic_1"], True)
    for key in PARENTS_BOTTOM_UP:
        expect_available(admin_page, syllabus_api, branch[key], False)


def test_mixed_subtopics_and_removing_last_content(admin_page, syllabus_api, branch, video_id):
    """Scenario: mixed subtopics -> parents stay Available while one child is Available;
    removing the last content makes the whole chain Not Available."""
    map_video(admin_page, video_id, branch, "subtopic_1")
    map_video(admin_page, video_id, branch, "subtopic_2")
    for key in ("subtopic_1", "subtopic_2", *PARENTS_BOTTOM_UP):
        set_available(admin_page, branch[key], True)

    unmap_videos(admin_page, branch, "subtopic_2")

    expect_available(admin_page, syllabus_api, branch["subtopic_1"], True)
    expect_available(admin_page, syllabus_api, branch["subtopic_2"], False)
    for key in PARENTS_BOTTOM_UP:
        expect_available(admin_page, syllabus_api, branch[key], True)

    unmap_videos(admin_page, branch, "subtopic_1")

    for key in ("subtopic_1", "subtopic_2", *PARENTS_BOTTOM_UP):
        expect_available(admin_page, syllabus_api, branch[key], False)


def test_restoring_content_requires_enabling_availability_again(admin_page, syllabus_api, branch, video_id):
    """Scenario: remove the last content, then restore it -> availability returns only after
    it is enabled again in each level's Edit popup."""
    map_video(admin_page, video_id, branch, "subtopic_1")
    for key in ("subtopic_1", *PARENTS_BOTTOM_UP):
        set_available(admin_page, branch[key], True)
    unmap_videos(admin_page, branch, "subtopic_1")
    for key in ("subtopic_1", *PARENTS_BOTTOM_UP):
        expect_available(admin_page, syllabus_api, branch[key], False)

    map_video(admin_page, video_id, branch, "subtopic_1")
    for key in ("subtopic_1", *PARENTS_BOTTOM_UP):
        expect_available(admin_page, syllabus_api, branch[key], False)

    for key in ("subtopic_1", *PARENTS_BOTTOM_UP):
        set_available(admin_page, branch[key], True)
    for key in ("subtopic_1", *PARENTS_BOTTOM_UP):
        expect_available(admin_page, syllabus_api, branch[key], True)


# ---------- Page UI, navigation and empty state ----------


def test_subtopic_list_page_ui_elements(level_page, qa_tree):
    check_list_page_ui(level_page, qa_tree["subtopic"])


def test_subtopic_breadcrumb_goes_back(level_page, qa_tree):
    check_breadcrumb_goes_back(level_page, qa_tree, "subtopic")


def test_subtopic_empty_state(level_page, syllabus_api, empty_parent):
    check_empty_state(level_page, syllabus_api, "subtopic", empty_parent)


# ---------- Cancel actions ----------


def test_subtopic_edit_popup_close_discards_changes(level_page, syllabus_api, qa_tree):
    check_edit_close_discards_changes(level_page, syllabus_api, qa_tree["subtopic"])


def test_subtopic_delete_can_be_cancelled(level_page, syllabus_api, qa_tree, level_item_name):
    check_delete_can_be_cancelled(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


# ---------- Invalid input, boundaries and duplicates ----------


def test_subtopic_whitespace_only_title_is_rejected(level_page, syllabus_api, qa_tree):
    check_whitespace_title_is_rejected(level_page, syllabus_api, qa_tree["subtopic"])


def test_subtopic_title_at_max_length_is_saved(level_page, syllabus_api, qa_tree, level_item_name):
    check_max_length_title_is_saved(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


def test_subtopic_title_over_max_length_is_rejected_without_server_error(level_page, syllabus_api, qa_tree, level_item_name):
    check_over_max_length_title_is_rejected(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


def test_subtopic_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_title_creates_separate_record(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


def test_subtopic_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_with_empty_title_is_rejected(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


# ---------- Persistence, Sort, Duplicate ----------


def test_subtopic_edit_persists_and_is_logged(level_page, syllabus_api, qa_tree, level_item_name):
    check_edit_persists_and_is_logged(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


def test_subtopic_sort_reorders_items(level_page, syllabus_api, qa_tree, level_item_name):
    check_sort_reorders_items(level_page, syllabus_api, qa_tree["subtopic"], level_item_name)


def test_duplicate_subtopic_creates_copy(level_page, syllabus_api, qa_tree, level_item_name):
    check_duplicate_creates_copy(level_page, syllabus_api, qa_tree, qa_tree["subtopic"], level_item_name)


# ---------- Server errors ----------


def test_subtopic_unknown_id_has_no_server_error(syllabus_api):
    check_unknown_id_has_no_server_error(syllabus_api, "subtopic")


# ---------- Subtopic fields ----------


def test_subtopic_pretest_shows_threshold(level_page):
    level_page.open_add_popup()
    expect(level_page.create_threshold_input).to_be_hidden()

    level_page.create_pretest_checkbox.check()
    expect(level_page.create_threshold_input).to_be_visible()
    expect(level_page.create_threshold_input).to_have_value(SubtopicPage.DEFAULT_THRESHOLD)

    level_page.create_pretest_checkbox.uncheck()
    expect(level_page.create_threshold_input).to_be_hidden()
