from uuid import uuid4

import pytest
from playwright.sync_api import expect

from pages.grade_page import GradePage


@pytest.fixture
def grade_page(content_dashboard):
    """Content Dashboard > Menu > Grade."""
    content_dashboard.open_menu_item("Grade")
    return GradePage(content_dashboard.page)


@pytest.fixture
def test_grade_name(grade_page):
    """Unique, test-only Grade name. Any Grade starting with it is deleted after the test."""
    name = f"QA Auto Grade {uuid4().hex[:8]}"
    yield name
    grade_page.delete_items_starting_with(name)


def test_grade_page_opens(grade_page):
    expect(grade_page.page).to_have_url(grade_page.url_pattern)
    expect(grade_page.heading).to_be_visible()
    expect(grade_page.add_button).to_be_visible()


def test_add_grade_popup_opens(grade_page):
    grade_page.open_add_popup()

    expect(grade_page.create_dialog).to_be_visible()
    expect(grade_page.create_title_input).to_be_visible()
    expect(grade_page.create_title_input).to_be_empty()
    expect(grade_page.create_title_input).to_have_attribute("required", "")
    expect(grade_page.create_save_button).to_be_visible()
    expect(grade_page.create_close_button).to_be_visible()


def test_add_grade_popup_can_be_closed(grade_page):
    grade_page.open_add_popup()
    expect(grade_page.create_dialog).to_be_visible()

    grade_page.close_add_popup()

    expect(grade_page.create_dialog).to_be_hidden()


def test_add_grade_required_field_validation(grade_page):
    items_before = grade_page.item_titles.count()

    grade_page.open_add_popup()
    grade_page.save_new_item()

    # Browser blocks submit because Title is required
    assert grade_page.is_create_title_missing()
    expect(grade_page.create_dialog).to_be_visible()
    expect(grade_page.page).to_have_url(grade_page.url_pattern)
    expect(grade_page.item_titles).to_have_count(items_before)


def test_add_grade_with_valid_data(grade_page, test_grade_name):
    grade_page.create_item(test_grade_name)

    expect(grade_page.success_alert).to_contain_text(grade_page.created_message)
    expect(grade_page.item_title(test_grade_name)).to_be_visible()


def test_edit_grade(grade_page, test_grade_name):
    updated_name = f"{test_grade_name} Updated"
    grade_page.create_item(test_grade_name)
    expect(grade_page.item_title(test_grade_name)).to_be_visible()

    grade_page.open_edit_popup(test_grade_name)
    expect(grade_page.update_dialog).to_be_visible()
    expect(grade_page.update_title_input).to_have_value(test_grade_name)

    grade_page.update_item_title(updated_name)

    expect(grade_page.page).to_have_url(grade_page.url_pattern)
    expect(grade_page.success_alert).to_contain_text(grade_page.updated_message)
    expect(grade_page.item_title(updated_name)).to_be_visible()
    expect(grade_page.item_title(test_grade_name)).to_have_count(0)


def test_delete_grade(grade_page, test_grade_name):
    grade_page.create_item(test_grade_name)
    expect(grade_page.item_title(test_grade_name)).to_be_visible()

    grade_page.open_delete_confirmation(test_grade_name)
    expect(grade_page.page).to_have_url(grade_page.delete_url_pattern)
    expect(grade_page.delete_page_heading).to_be_visible()
    expect(grade_page.delete_page_items).to_have_text([test_grade_name])

    grade_page.open_delete_confirm_popup()
    expect(grade_page.delete_confirm_dialog).to_be_visible()
    grade_page.accept_delete_confirm_popup()

    expect(grade_page.page).to_have_url(grade_page.url_pattern)
    expect(grade_page.success_alert).to_contain_text(grade_page.deleted_message)
    expect(grade_page.item_title(test_grade_name)).to_have_count(0)
