from uuid import uuid4

import pytest
from playwright.sync_api import expect

from pages.medium_page import MediumPage


@pytest.fixture
def medium_page(content_dashboard):
    """Content Dashboard > Menu > Medium."""
    content_dashboard.open_menu_item("Medium")
    return MediumPage(content_dashboard.page)


@pytest.fixture
def test_medium_name(medium_page):
    """Unique, test-only Medium name. Any Medium starting with it is deleted after the test."""
    name = f"QA Auto Medium {uuid4().hex[:8]}"
    yield name
    medium_page.delete_items_starting_with(name)


def test_medium_page_opens(medium_page):
    expect(medium_page.page).to_have_url(medium_page.url_pattern)
    expect(medium_page.heading).to_be_visible()
    expect(medium_page.add_button).to_be_visible()


def test_add_medium_popup_opens(medium_page):
    medium_page.open_add_popup()

    expect(medium_page.create_dialog).to_be_visible()
    expect(medium_page.create_title_input).to_be_visible()
    expect(medium_page.create_title_input).to_be_empty()
    expect(medium_page.create_title_input).to_have_attribute("required", "")
    expect(medium_page.create_save_button).to_be_visible()
    expect(medium_page.create_close_button).to_be_visible()


def test_add_medium_popup_can_be_closed(medium_page):
    medium_page.open_add_popup()
    expect(medium_page.create_dialog).to_be_visible()

    medium_page.close_add_popup()

    expect(medium_page.create_dialog).to_be_hidden()


def test_add_medium_required_field_validation(medium_page):
    items_before = medium_page.item_titles.count()

    medium_page.open_add_popup()
    medium_page.save_new_item()

    # Browser blocks submit because Title is required
    assert medium_page.is_create_title_missing()
    expect(medium_page.create_dialog).to_be_visible()
    expect(medium_page.page).to_have_url(medium_page.url_pattern)
    expect(medium_page.item_titles).to_have_count(items_before)


def test_add_medium_with_valid_data(medium_page, test_medium_name):
    medium_page.create_item(test_medium_name)

    expect(medium_page.success_alert).to_contain_text(medium_page.created_message)
    expect(medium_page.item_title(test_medium_name)).to_be_visible()


def test_edit_medium(medium_page, test_medium_name):
    updated_name = f"{test_medium_name} Updated"
    medium_page.create_item(test_medium_name)
    expect(medium_page.item_title(test_medium_name)).to_be_visible()

    medium_page.open_edit_popup(test_medium_name)
    expect(medium_page.update_dialog).to_be_visible()
    expect(medium_page.update_title_input).to_have_value(test_medium_name)

    medium_page.update_item_title(updated_name)

    expect(medium_page.page).to_have_url(medium_page.url_pattern)
    expect(medium_page.success_alert).to_contain_text(medium_page.updated_message)
    expect(medium_page.item_title(updated_name)).to_be_visible()
    expect(medium_page.item_title(test_medium_name)).to_have_count(0)


def test_delete_medium(medium_page, test_medium_name):
    medium_page.create_item(test_medium_name)
    expect(medium_page.item_title(test_medium_name)).to_be_visible()

    medium_page.open_delete_confirmation(test_medium_name)
    expect(medium_page.page).to_have_url(medium_page.delete_url_pattern)
    expect(medium_page.delete_page_heading).to_be_visible()
    expect(medium_page.delete_page_items).to_have_text([test_medium_name])

    medium_page.open_delete_confirm_popup()
    expect(medium_page.delete_confirm_dialog).to_be_visible()
    medium_page.accept_delete_confirm_popup()

    expect(medium_page.page).to_have_url(medium_page.url_pattern)
    expect(medium_page.success_alert).to_contain_text(medium_page.deleted_message)
    expect(medium_page.item_title(test_medium_name)).to_have_count(0)
