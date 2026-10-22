"""Shared steps and checks for the course content hierarchy tests
(test_subject.py, test_chapter.py, test_topic.py, test_subtopic.py).

Items are passed around as dicts: {"level", "id", "name", "parent"}, where "parent" is
the id of the parent record (the course id for a Subject).
"""

from playwright.sync_api import expect

from api.syllabus_api import SyllabusApi
from pages.chapter_page import ChapterPage
from pages.subject_page import SubjectPage
from pages.subtopic_page import SubtopicPage
from pages.course_page import CoursePage
from config import BASE_URL
from pages.syllabus_level_page import ChangeLogPage
from pages.topic_page import TopicPage
from pages.video_mapping_page import MappedVideosPage, VideoMapPage

LEVEL_PAGES = {"subject": SubjectPage, "chapter": ChapterPage, "topic": TopicPage, "subtopic": SubtopicPage}
PARENT_LEVEL = {"subject": "course", "chapter": "subject", "topic": "chapter", "subtopic": "topic"}
PARENTS_BOTTOM_UP = ("topic", "chapter", "subject")
UNKNOWN_ID = "99999999"


def ancestor_ids(qa_tree: dict, level: str) -> list[str]:
    """Ids from the course down to the parent of `level` in the shared QA branch."""
    chain = [qa_tree["course"]] + [qa_tree[name]["id"] for name in ("subject", "chapter", "topic")]
    return chain[: list(LEVEL_PAGES).index(level) + 1]


def item_titles(api: SyllabusApi, parent_id: str, level: str) -> list[str]:
    return [child["title"] for child in api.children(parent_id, level)]


# ---------- Building test data ----------


def create_branch(page, course_id: str, tag: str, subtopics: int = 1) -> dict:
    """Create Subject > Chapter > Topic > `subtopics` Subtopic(s) under a course.

    Returns {key: item} with keys subject, chapter, topic, subtopic_1, subtopic_2, ...
    """
    branch = {}
    parent = course_id
    keys = ["subject", "chapter", "topic"] + [f"subtopic_{i}" for i in range(1, subtopics + 1)]
    for key in keys:
        level = key.split("_")[0]
        level_page = LEVEL_PAGES[level](page)
        name = f"QA Auto {level_page.LEVEL} {tag}" + (f" {key[-1]}" if level == "subtopic" else "")
        level_page.open(parent)
        level_page.create_item(name)
        branch[key] = {"level": level, "id": level_page.item_id(name), "name": name, "parent": parent}
        if level != "subtopic":
            parent = branch[key]["id"]
    return branch


def map_video(page, video_id: str, branch: dict, subtopic_key: str) -> None:
    video_map = VideoMapPage(page)
    video_map.open(video_id)
    video_map.map_to_subtopic(
        branch["subject"]["parent"],
        branch["subject"]["id"],
        branch["chapter"]["id"],
        branch["topic"]["id"],
        branch[subtopic_key]["id"],
    )
    expect(page.get_by_role("alert").filter(has_text=VideoMapPage.MAPPED_MESSAGE)).to_be_visible()


def unmap_videos(page, branch: dict, subtopic_key: str) -> None:
    MappedVideosPage(page).unmap_all(branch[subtopic_key]["id"])


def set_available(page, item: dict, available: bool):
    level_page = LEVEL_PAGES[item["level"]](page)
    level_page.open(item["parent"])
    level_page.set_availability(item["name"], available)
    return level_page


# ---------- Checks ----------


def expect_available(page, api: SyllabusApi, item: dict, available: bool) -> None:
    """Check availability in the UI badge and in the server's Edit form (UI vs API)."""
    level_page = LEVEL_PAGES[item["level"]](page)
    level_page.open(item["parent"])
    expected = level_page.AVAILABLE if available else level_page.NOT_AVAILABLE
    expect(level_page.card_status_badge(item["name"]), f"{item['name']} badge").to_have_text(expected)
    # Server Edit form: "Is Available" is offered (unticked) only while Not Available
    expected_field = None if available else False
    assert api.availability_field(item["level"], item["id"]) is expected_field, f"{item['name']} API availability"


def check_opened_level(level_page, item: dict, parent_names: list[str]) -> None:
    """The level's list page for `item`'s parent is open and shows the item."""
    expect(level_page.page).to_have_url(f"{BASE_URL}/core/{item['level']}/list/{item['parent']}")
    expect(level_page.heading).to_be_visible()
    for parent_name in parent_names:
        expect(level_page.breadcrumb).to_contain_text(parent_name)
    expect(level_page.card(item["name"])).to_be_visible()


def check_api_children_match_ui(level_page, api: SyllabusApi, item: dict) -> None:
    level_page.open(item["parent"])
    api_children = api.children(item["parent"], item["level"])

    assert api.child_ids_and_titles(item["parent"], item["level"]) == level_page.card_ids_and_titles()
    assert {child["syllabus_type"] for child in api_children} == {SyllabusApi.SYLLABUS_TYPES[item["level"]]}
    assert str(item["id"]) in {str(child["id"]) for child in api_children}


def check_create_popup_opens_and_closes(level_page) -> None:
    level_page.open_add_popup()
    expect(level_page.create_dialog).to_be_visible()
    expect(level_page.create_title_input).to_be_empty()
    expect(level_page.create_save_button).to_be_visible()

    level_page.close_add_popup()
    expect(level_page.create_dialog).to_be_hidden()


def check_create_required_field_validation(level_page) -> None:
    cards_before = level_page.cards.count()

    level_page.open_add_popup()
    for field in level_page.CREATE_REQUIRED_FIELDS:
        expect(level_page.create_field(field)).to_have_attribute("required", "")
    level_page.save_new_item()

    assert level_page.is_create_title_missing()
    expect(level_page.create_dialog).to_be_visible()
    expect(level_page.page).to_have_url(level_page.list_url_pattern)
    expect(level_page.cards).to_have_count(cards_before)


def check_create_appears_under_parent(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    level_page.create_item(name)

    expect(level_page.alert(level_page.created_message)).to_be_visible()
    expect(level_page.card(name)).to_be_visible()
    expect(level_page.card_status_badge(name)).to_have_text(level_page.NOT_AVAILABLE)
    new_id = level_page.item_id(name)
    assert api.child_ids_and_titles(parent_id, level).get(str(new_id)) == name
    # The existing sibling under the same parent is untouched
    expect(level_page.card(shared_item["name"])).to_be_visible()


def check_edit_updates_details(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    updated_name = f"{name} Updated"
    level_page.create_item(name)
    item_id = level_page.item_id(name)

    level_page.open_edit_popup(name)
    expect(level_page.update_dialog).to_be_visible()
    expect(level_page.update_title_input).to_have_value(name)
    level_page.update_title_input.fill(updated_name)
    level_page.save_edit()

    expect(level_page.alert(level_page.updated_message)).to_be_visible()
    expect(level_page.card(updated_name)).to_be_visible()
    expect(level_page.card(name)).to_have_count(0)
    assert api.child_ids_and_titles(parent_id, level).get(str(item_id)) == updated_name


def check_delete_removes_record(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    level_page.create_item(name)
    item_id = level_page.item_id(name)

    level_page.open_delete_confirmation(name)
    expect(level_page.delete_page_heading).to_be_visible()
    expect(level_page.delete_page_item(name)).to_be_visible()
    level_page.open_delete_confirm_popup()
    expect(level_page.delete_confirm_dialog).to_be_visible()
    level_page.accept_delete_confirm_popup()

    expect(level_page.alert(level_page.deleted_message)).to_be_visible()
    expect(level_page.card(name)).to_have_count(0)
    remaining = api.child_ids_and_titles(parent_id, level)
    assert str(item_id) not in remaining
    # Parent-child relationships of the existing branch remain intact
    assert str(shared_item["id"]) in remaining


# ---------- Page UI, navigation and empty state ----------


def check_list_page_ui(level_page, item: dict) -> None:
    expect(level_page.heading).to_be_visible()
    expect(level_page.breadcrumb).to_be_visible()
    expect(level_page.add_button).to_be_visible()
    expect(level_page.sort_button).to_be_visible()
    expect(level_page.card_status_badge(item["name"])).to_be_visible()
    assert level_page.card_menu_items(item["name"]) == list(level_page.MENU_ITEMS)

    level_page.open_add_popup()
    if level_page.CREATE_HAS_AVAILABILITY:
        # "Is Available" is shown but disabled on create ("available on update")
        expect(level_page.create_availability).to_be_disabled()
    else:
        expect(level_page.create_availability).to_have_count(0)
    level_page.close_add_popup()


def check_breadcrumb_goes_back(level_page, qa_tree: dict, level: str) -> None:
    level_page.open(qa_tree[level]["parent"])
    if level == "subject":
        with level_page.page.expect_navigation(wait_until="domcontentloaded"):
            level_page.breadcrumb_home_link.click()
        expect(level_page.page).to_have_url(CoursePage.URL_PATTERN)
        return
    parent_level = PARENT_LEVEL[level]
    grandparent_level = PARENT_LEVEL[parent_level]
    grandparent_name = qa_tree["course_name"] if grandparent_level == "course" else qa_tree[grandparent_level]["name"]
    with level_page.page.expect_navigation(wait_until="domcontentloaded"):
        level_page.breadcrumb_link(grandparent_name).click()
    check_opened_level(LEVEL_PAGES[parent_level](level_page.page), qa_tree[parent_level], [])


def check_empty_state(level_page, api: SyllabusApi, level: str, parent_id: str) -> None:
    level_page.open(parent_id)

    expect(level_page.heading).to_be_visible()
    expect(level_page.add_button).to_be_visible()
    expect(level_page.cards).to_have_count(0)
    assert api.children(parent_id, level) == []


# ---------- Cancel actions ----------


def check_edit_close_discards_changes(level_page, api: SyllabusApi, item: dict) -> None:
    level_page.open_edit_popup(item["name"])
    level_page.update_title_input.fill(f"{item['name']} NOT SAVED")
    level_page.close_edit_popup()
    expect(level_page.update_dialog).to_be_hidden()

    level_page.open(item["parent"])
    expect(level_page.card(item["name"])).to_be_visible()
    expect(level_page.card(f"{item['name']} NOT SAVED")).to_have_count(0)
    assert api.child_ids_and_titles(item["parent"], item["level"]).get(str(item["id"])) == item["name"]


def check_delete_can_be_cancelled(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    level_page.create_item(name)
    item_id = str(level_page.item_id(name))

    # Close on the confirmation page goes back without deleting
    level_page.open_delete_confirmation(name)
    level_page.cancel_on_delete_page()
    expect(level_page.page).to_have_url(level_page.list_url_pattern)
    expect(level_page.card(name)).to_be_visible()
    assert item_id in api.child_ids_and_titles(parent_id, level)

    # Close in the final "Are you sure" popup does not delete either
    level_page.open_delete_confirmation(name)
    level_page.open_delete_confirm_popup()
    expect(level_page.delete_confirm_dialog).to_be_visible()
    level_page.delete_confirm_close_button.click()
    expect(level_page.delete_confirm_dialog).to_be_hidden()
    assert item_id in api.child_ids_and_titles(parent_id, level)


# ---------- Invalid input, boundaries and duplicates ----------


def check_whitespace_title_is_rejected(level_page, api: SyllabusApi, shared_item: dict) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    before = set(api.child_ids_and_titles(parent_id, level))

    level_page.submit_new_item("   ")

    created = {i: t for i, t in api.child_ids_and_titles(parent_id, level).items() if i not in before}
    assert created == {}, f"A {level} with a blank title was created: {created}"


def check_max_length_title_is_saved(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    title = f"{name} ".ljust(level_page.TITLE_MAX_LENGTH, "x")

    level_page.create_item(title)

    expect(level_page.alert(level_page.created_message)).to_be_visible()
    expect(level_page.card(title)).to_be_visible()
    assert title in item_titles(api, shared_item["parent"], shared_item["level"])


def check_over_max_length_title_is_rejected(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    title = f"{name} ".ljust(level_page.TITLE_MAX_LENGTH + 1, "x")

    status = level_page.submit_new_item(title)

    assert status is None or status < 500, f"Create returned HTTP {status} (server error) for a {len(title)}-char title"
    assert title not in item_titles(api, shared_item["parent"], shared_item["level"])


def check_duplicate_title_creates_separate_record(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    """Current behaviour: titles are not unique within a parent (no rule found in UI or API)."""
    level_page.create_item(name)
    level_page.open(shared_item["parent"])
    level_page.create_item(name)

    expect(level_page.alert(level_page.created_message)).to_be_visible()
    expect(level_page.card(name)).to_have_count(2)
    ids = [i for i, t in api.child_ids_and_titles(shared_item["parent"], shared_item["level"]).items() if t == name]
    assert len(set(ids)) == 2


def check_edit_with_empty_title_is_rejected(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    level_page.create_item(name)
    item_id = str(level_page.item_id(name))

    level_page.submit_edit_title(name, "")

    assert api.child_ids_and_titles(parent_id, level).get(item_id) == name, "Title was saved empty"


# ---------- Persistence, Sort, Duplicate ----------


def check_edit_persists_and_is_logged(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    updated_name = f"{name} Updated"
    level_page.create_item(name)
    item_id = str(level_page.item_id(name))
    level_page.update_title(name, updated_name)

    # Re-opening the Edit popup after a reload shows the saved value
    level_page.open(parent_id)
    level_page.open_edit_popup(updated_name)
    expect(level_page.update_title_input).to_have_value(updated_name)
    level_page.close_edit_popup()
    assert api.edit_form_values(level, item_id)["title"] == updated_name

    if "Change Log" in level_page.MENU_ITEMS:
        level_page.open_change_log(updated_name)
        change_log = ChangeLogPage(level_page.page, level_page.LEVEL)
        expect(change_log.heading).to_be_visible()
        events = change_log.event_names()
        assert events[:2] == ["Updated", "Created"], f"{level_page.LEVEL} Change Log events: {events}"
        expect(change_log.event_data.first).to_contain_text(f"'title': '{updated_name}'")


def check_sort_reorders_items(level_page, api: SyllabusApi, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    first, second = f"{name} A", f"{name} B"
    level_page.create_item(first)
    level_page.create_item(second)
    order_before = level_page.ordered_card_titles()

    # The Sort popup lists the same items; Close keeps the order
    level_page.open_sort_popup()
    expect(level_page.sort_dialog).to_be_visible()
    assert level_page.sort_card_titles() == order_before
    level_page.close_sort_popup()
    expect(level_page.sort_dialog).to_be_hidden()
    level_page.open(parent_id)
    assert level_page.ordered_card_titles() == order_before

    # Drag the second item before the first and save
    level_page.open_sort_popup()
    level_page.sort_move_before(second, first)
    level_page.save_sort()

    expect(level_page.alert(level_page.sorted_message)).to_be_visible()
    ui_order = level_page.ordered_card_titles()
    api_order = item_titles(api, parent_id, level)
    assert ui_order.index(second) < ui_order.index(first)
    assert api_order.index(second) < api_order.index(first)


def check_duplicate_creates_copy(level_page, api: SyllabusApi, qa_tree: dict, shared_item: dict, name: str) -> None:
    level, parent_id = shared_item["level"], shared_item["parent"]
    copy_name = f"{name}{level_page.COPY_SUFFIX}"
    level_page.create_item(name)

    level_page.duplicate_item(name, ancestor_ids(qa_tree, level))

    expect(level_page.alert(level_page.DUPLICATE_MESSAGE)).to_be_visible()
    level_page.open(parent_id)
    expect(level_page.card(copy_name)).to_be_visible()
    expect(level_page.card(name)).to_be_visible()
    titles = item_titles(api, parent_id, level)
    assert copy_name in titles and name in titles


# ---------- Server errors ----------


def check_unknown_id_has_no_server_error(api: SyllabusApi, level: str) -> None:
    edit_form = api.get_edit_form(level, UNKNOWN_ID)
    list_page = api.get_list_page(level, UNKNOWN_ID)

    assert edit_form.status < 500, f"Edit form for unknown {level} id returned HTTP {edit_form.status}"
    assert list_page.status < 500, f"{level} list for unknown parent id returned HTTP {list_page.status}"
