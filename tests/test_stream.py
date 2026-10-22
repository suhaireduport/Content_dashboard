from uuid import uuid4

import pytest
from playwright.sync_api import expect

from pages.stream_page import StreamPage


@pytest.fixture
def stream_page(content_dashboard):
    """Content Dashboard > Menu > Stream."""
    content_dashboard.open_menu_item("Stream")
    return StreamPage(content_dashboard.page)


@pytest.fixture
def test_stream_name(stream_page):
    """Unique, test-only Stream name. Any Stream starting with it is deleted after the test."""
    name = f"QA Auto Stream {uuid4().hex[:8]}"
    yield name
    stream_page.delete_items_starting_with(name)


def test_stream_page_opens(stream_page):
    expect(stream_page.page).to_have_url(stream_page.url_pattern)
    expect(stream_page.heading).to_be_visible()
    expect(stream_page.add_button).to_be_visible()


def test_add_stream_popup_opens(stream_page):
    stream_page.open_add_popup()

    expect(stream_page.create_dialog).to_be_visible()
    expect(stream_page.create_title_input).to_be_visible()
    expect(stream_page.create_title_input).to_be_empty()
    expect(stream_page.create_title_input).to_have_attribute("required", "")
    expect(stream_page.create_save_button).to_be_visible()
    expect(stream_page.create_close_button).to_be_visible()


def test_add_stream_popup_can_be_closed(stream_page):
    stream_page.open_add_popup()
    expect(stream_page.create_dialog).to_be_visible()

    stream_page.close_add_popup()

    expect(stream_page.create_dialog).to_be_hidden()


def test_add_stream_required_field_validation(stream_page):
    items_before = stream_page.item_titles.count()

    stream_page.open_add_popup()
    stream_page.save_new_item()

    # Browser blocks submit because Title is required
    assert stream_page.is_create_title_missing()
    expect(stream_page.create_dialog).to_be_visible()
    expect(stream_page.page).to_have_url(stream_page.url_pattern)
    expect(stream_page.item_titles).to_have_count(items_before)


def test_add_stream_with_valid_data(stream_page, test_stream_name):
    stream_page.create_item(test_stream_name)

    expect(stream_page.success_alert).to_contain_text(stream_page.created_message)
    expect(stream_page.item_title(test_stream_name)).to_be_visible()


def test_edit_stream(stream_page, test_stream_name):
    updated_name = f"{test_stream_name} Updated"
    stream_page.create_item(test_stream_name)
    expect(stream_page.item_title(test_stream_name)).to_be_visible()

    stream_page.open_edit_popup(test_stream_name)
    expect(stream_page.update_dialog).to_be_visible()
    expect(stream_page.update_title_input).to_have_value(test_stream_name)

    stream_page.update_item_title(updated_name)

    expect(stream_page.page).to_have_url(stream_page.url_pattern)
    expect(stream_page.success_alert).to_contain_text(stream_page.updated_message)
    expect(stream_page.item_title(updated_name)).to_be_visible()
    expect(stream_page.item_title(test_stream_name)).to_have_count(0)


def test_delete_stream(stream_page, test_stream_name):
    stream_page.create_item(test_stream_name)
    expect(stream_page.item_title(test_stream_name)).to_be_visible()

    stream_page.open_delete_confirmation(test_stream_name)
    expect(stream_page.page).to_have_url(stream_page.delete_url_pattern)
    expect(stream_page.delete_page_heading).to_be_visible()
    expect(stream_page.delete_page_items).to_have_text([test_stream_name])

    stream_page.open_delete_confirm_popup()
    expect(stream_page.delete_confirm_dialog).to_be_visible()
    stream_page.accept_delete_confirm_popup()

    expect(stream_page.page).to_have_url(stream_page.url_pattern)
    expect(stream_page.success_alert).to_contain_text(stream_page.deleted_message)
    expect(stream_page.item_title(test_stream_name)).to_have_count(0)
