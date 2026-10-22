from uuid import uuid4

import pytest
from playwright.sync_api import expect

from api.course_api import CourseApi
from pages.course_page import CoursePage
from tests.data import COURSE_DATA


@pytest.fixture
def test_course_name(course_page):
    """Unique, test-only Course name. Any Course starting with it is deleted after the test."""
    name = f"QA Auto Course {uuid4().hex[:8]}"
    yield name
    course_page.delete_courses_starting_with(name)


@pytest.fixture
def course_api(course_page):
    """API client sharing the logged-in browser session (cookies)."""
    return CourseApi(course_page.page.request)


@pytest.fixture
def anonymous_course_api(browser):
    """API client with a fresh, logged-out session."""
    context = browser.new_context()
    yield CourseApi(context.request)
    context.close()


# ---------- Page and tabs ----------


def test_course_page_opens(course_page):
    expect(course_page.page).to_have_url(CoursePage.URL_PATTERN)
    expect(course_page.heading).to_be_visible()
    expect(course_page.add_button).to_be_visible()


def test_course_status_tabs_available(course_page):
    expect(course_page.active_tab).to_be_visible()
    expect(course_page.archived_tab).to_be_visible()
    expect(course_page.all_tab).to_be_visible()
    # Active is the default tab
    expect(course_page.active_tab).to_have_attribute("aria-selected", "true")


def test_active_tab_shows_only_active_courses(course_page):
    course_page.show_active()

    expect(course_page.visible_archived_cards).to_have_count(0)
    expect(course_page.visible_active_cards).to_have_count(course_page.tab_count(course_page.active_count))
    expect(course_page.visible_cards.locator(".badge").filter(has_text=CoursePage.ARCHIVED_STATUS)).to_have_count(0)


def test_archived_tab_shows_only_non_active_courses(course_page):
    course_page.show_archived()

    expect(course_page.visible_active_cards).to_have_count(0)
    expect(course_page.visible_archived_cards).to_have_count(course_page.tab_count(course_page.archived_count))
    expect(course_page.visible_cards.locator(".badge").filter(has_text=CoursePage.ACTIVE_STATUS)).to_have_count(0)


def test_all_tab_shows_active_and_non_active_courses(course_page):
    course_page.show_all()

    active = course_page.tab_count(course_page.active_count)
    archived = course_page.tab_count(course_page.archived_count)
    total = course_page.tab_count(course_page.all_count)

    assert active > 0 and archived > 0, "Need both active and archived courses in the data"
    assert total == active + archived
    expect(course_page.visible_cards).to_have_count(total)
    expect(course_page.visible_active_cards).to_have_count(active)
    expect(course_page.visible_archived_cards).to_have_count(archived)


# ---------- Create ----------


def test_add_course_popup_opens(course_page):
    course_page.open_add_popup()

    expect(course_page.create_dialog).to_be_visible()
    expect(course_page.create_title_input).to_be_empty()
    expect(course_page.create_title_input).to_have_attribute("required", "")
    expect(course_page.create_academic_year).to_have_attribute("required", "")
    for field in (
        course_page.create_zoho_item,
        course_page.create_board,
        course_page.create_grade,
        course_page.create_medium,
        course_page.create_stream,
    ):
        expect(field).to_be_visible()
    expect(course_page.create_is_active).to_be_checked()
    expect(course_page.create_save_button).to_be_visible()
    expect(course_page.create_close_button).to_be_visible()


def test_add_course_popup_can_be_closed(course_page):
    course_page.open_add_popup()
    expect(course_page.create_dialog).to_be_visible()

    course_page.close_add_popup()

    expect(course_page.create_dialog).to_be_hidden()


def test_add_course_required_field_validation(course_page):
    total_before = course_page.tab_count(course_page.all_count)

    course_page.open_add_popup()
    course_page.save_new_course()

    # Browser blocks submit because Title is required
    assert course_page.is_create_title_missing()
    expect(course_page.create_dialog).to_be_visible()
    expect(course_page.page).to_have_url(CoursePage.URL_PATTERN)
    expect(course_page.all_count).to_have_text(str(total_before))


def test_add_active_course_appears_in_active_and_all(course_page, test_course_name):
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=True)

    expect(course_page.success_alert).to_contain_text(CoursePage.CREATED_MESSAGE)
    card = course_page.course_card(test_course_name)
    expect(card).to_have_count(1)
    expect(card).to_have_attribute("data-active", "true")
    expect(course_page.course_status_badge(test_course_name)).to_have_text(CoursePage.ACTIVE_STATUS)
    expect(course_page.course_detail(test_course_name, "Board")).to_have_text(COURSE_DATA["board"])
    expect(course_page.course_detail(test_course_name, "Grade")).to_have_text(COURSE_DATA["grade"])
    expect(course_page.course_detail(test_course_name, "Stream")).to_have_text(COURSE_DATA["stream"])
    expect(course_page.course_detail(test_course_name, "Medium")).to_have_text(COURSE_DATA["medium"])

    course_page.show_active()
    expect(card).to_be_visible()
    course_page.show_archived()
    expect(card).to_be_hidden()
    course_page.show_all()
    expect(card).to_be_visible()


def test_add_non_active_course_appears_in_archived_and_all(course_page, test_course_name):
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=False)

    expect(course_page.success_alert).to_contain_text(CoursePage.CREATED_MESSAGE)
    card = course_page.course_card(test_course_name)
    expect(card).to_have_count(1)
    expect(card).to_have_attribute("data-active", "false")
    expect(course_page.course_status_badge(test_course_name)).to_have_text(CoursePage.ARCHIVED_STATUS)

    course_page.show_active()
    expect(card).to_be_hidden()
    course_page.show_archived()
    expect(card).to_be_visible()
    course_page.show_all()
    expect(card).to_be_visible()


# ---------- Edit ----------


def test_edit_course_form_shows_existing_values(course_page, test_course_name):
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=True)

    course_page.open_edit_popup(test_course_name)

    expect(course_page.update_dialog).to_be_visible()
    expect(course_page.update_title_input).to_have_value(test_course_name)
    expect(course_page.update_academic_year).to_have_value(COURSE_DATA["academic_year"])
    for select, expected in (
        (course_page.update_zoho_item, COURSE_DATA["zoho_item"]),
        (course_page.update_board, COURSE_DATA["board"]),
        (course_page.update_grade, COURSE_DATA["grade"]),
        (course_page.update_medium, COURSE_DATA["medium"]),
        (course_page.update_stream, COURSE_DATA["stream"]),
    ):
        expect(select.locator("option:checked")).to_have_text(expected)
    expect(course_page.update_is_active).to_be_checked()


def test_edit_course_save_requires_default_batch(course_page, test_course_name):
    """A new course has no batches, and the Update form requires 'Default Batch',
    so the browser blocks Save and the course is not changed."""
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=True)
    course_page.open_edit_popup(test_course_name)
    expect(course_page.update_title_input).to_have_value(test_course_name)

    course_page.change_title_and_save(f"{test_course_name} Updated")

    assert course_page.is_default_batch_missing()
    expect(course_page.update_dialog).to_be_visible()
    expect(course_page.page).to_have_url(CoursePage.URL_PATTERN)
    expect(course_page.course_card(test_course_name)).to_have_count(1)


# ---------- Delete ----------


def test_delete_course(course_page, test_course_name):
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=True)
    expect(course_page.course_card(test_course_name)).to_have_count(1)

    course_page.open_delete_confirmation(test_course_name)
    expect(course_page.page).to_have_url(CoursePage.DELETE_URL_PATTERN)
    expect(course_page.delete_page_heading).to_be_visible()
    expect(course_page.delete_page_item(test_course_name)).to_be_visible()

    course_page.open_delete_confirm_popup()
    expect(course_page.delete_confirm_dialog).to_be_visible()
    course_page.accept_delete_confirm_popup()

    expect(course_page.page).to_have_url(CoursePage.URL_PATTERN)
    expect(course_page.success_alert).to_contain_text(CoursePage.DELETED_MESSAGE)
    expect(course_page.course_card(test_course_name)).to_have_count(0)


# ---------- API: endpoint basics ----------


def test_course_list_endpoint_requires_login(anonymous_course_api):
    response = anonymous_course_api.get_list(follow_redirects=False)

    assert response.status == 302
    assert response.headers["location"].startswith(CourseApi.LOGIN_REDIRECT_PREFIX)


def test_course_list_endpoint_returns_html(course_api):
    response = course_api.get_list()

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/html")


# ---------- API: server data vs UI ----------


def test_api_courses_match_ui_cards_and_tab_counts(course_page, course_api):
    api_courses = course_api.list_courses()
    api_statuses = {course["id"]: course["active"] for course in api_courses}

    assert api_statuses == course_page.card_statuses()

    active = sum(api_statuses.values())
    expect(course_page.active_count).to_have_text(str(active))
    expect(course_page.archived_count).to_have_text(str(len(api_statuses) - active))
    expect(course_page.all_count).to_have_text(str(len(api_statuses)))


def test_created_course_is_returned_by_api(course_page, course_api, test_course_name):
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=True)
    expect(course_page.course_card(test_course_name)).to_have_count(1)

    api_matches = course_api.find_courses(test_course_name)

    assert len(api_matches) == 1
    assert api_matches[0]["id"] == course_page.course_id(test_course_name)
    assert api_matches[0]["active"] is True


def test_api_edit_form_returns_created_course_values(course_page, course_api, test_course_name):
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=True)
    course_id = course_page.course_id(test_course_name)

    response = course_api.get_edit_form(course_id)
    assert response.status == 200
    values = course_api.edit_form_values(course_id)

    assert values["title"] == test_course_name
    assert values["academic_year"] == COURSE_DATA["academic_year"]
    assert values["zoho_item_id"] == COURSE_DATA["zoho_item"]
    assert values["board"] == COURSE_DATA["board"]
    assert values["grade"] == COURSE_DATA["grade"]
    assert values["medium"] == COURSE_DATA["medium"]
    assert values["stream"] == COURSE_DATA["stream"]
    assert values["is_active"] is True


def test_deleted_course_is_removed_from_api(course_page, course_api, test_course_name):
    course_page.create_course(test_course_name, **COURSE_DATA, is_active=True)
    assert len(course_api.find_courses(test_course_name)) == 1

    course_page.delete_course(test_course_name)
    expect(course_page.success_alert).to_contain_text(CoursePage.DELETED_MESSAGE)

    assert course_api.find_courses(test_course_name) == []
