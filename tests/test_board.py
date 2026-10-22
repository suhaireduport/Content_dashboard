from uuid import uuid4

import pytest
from playwright.sync_api import expect

from pages.board_page import BoardPage


@pytest.fixture
def board_page(content_dashboard):
    """Content Dashboard > Menu > Board."""
    content_dashboard.open_menu_item("Board")
    return BoardPage(content_dashboard.page)


@pytest.fixture
def test_board_name(board_page):
    """Unique, test-only board name. Any board starting with it is deleted after the test."""
    name = f"QA Auto Board {uuid4().hex[:8]}"
    yield name
    board_page.delete_boards_starting_with(name)


def test_board_page_opens(board_page):
    expect(board_page.page).to_have_url(BoardPage.URL_PATTERN)
    expect(board_page.heading).to_be_visible()
    expect(board_page.add_button).to_be_visible()


def test_add_board_popup_opens(board_page):
    board_page.open_add_popup()

    expect(board_page.create_dialog).to_be_visible()
    expect(board_page.create_title_input).to_be_visible()
    expect(board_page.create_title_input).to_be_empty()
    expect(board_page.create_title_input).to_have_attribute("required", "")
    expect(board_page.create_save_button).to_be_visible()
    expect(board_page.create_close_button).to_be_visible()


def test_add_board_popup_can_be_closed(board_page):
    board_page.open_add_popup()
    expect(board_page.create_dialog).to_be_visible()

    board_page.close_add_popup()

    expect(board_page.create_dialog).to_be_hidden()


def test_add_board_required_field_validation(board_page):
    boards_before = board_page.board_titles.count()

    board_page.open_add_popup()
    board_page.save_new_board()

    # Browser blocks submit because Title is required
    assert board_page.is_create_title_missing()
    expect(board_page.create_dialog).to_be_visible()
    expect(board_page.page).to_have_url(BoardPage.URL_PATTERN)
    expect(board_page.board_titles).to_have_count(boards_before)


def test_add_board_with_valid_data(board_page, test_board_name):
    board_page.create_board(test_board_name)

    expect(board_page.success_alert).to_contain_text(BoardPage.CREATED_MESSAGE)
    expect(board_page.board_title(test_board_name)).to_be_visible()


def test_edit_board(board_page, test_board_name):
    updated_name = f"{test_board_name} Updated"
    board_page.create_board(test_board_name)
    expect(board_page.board_title(test_board_name)).to_be_visible()

    board_page.open_edit_popup(test_board_name)
    expect(board_page.update_dialog).to_be_visible()
    expect(board_page.update_title_input).to_have_value(test_board_name)

    board_page.update_board_title(updated_name)

    expect(board_page.page).to_have_url(BoardPage.URL_PATTERN)
    expect(board_page.board_title(updated_name)).to_be_visible()
    expect(board_page.board_title(test_board_name)).to_have_count(0)


def test_delete_board(board_page, test_board_name):
    board_page.create_board(test_board_name)
    expect(board_page.board_title(test_board_name)).to_be_visible()

    board_page.open_delete_confirmation(test_board_name)
    expect(board_page.page).to_have_url(BoardPage.DELETE_URL_PATTERN)
    expect(board_page.delete_page_heading).to_be_visible()
    expect(board_page.delete_page_items).to_have_text([test_board_name])

    board_page.open_delete_confirm_popup()
    expect(board_page.delete_confirm_dialog).to_be_visible()
    board_page.accept_delete_confirm_popup()

    expect(board_page.page).to_have_url(BoardPage.URL_PATTERN)
    expect(board_page.board_title(test_board_name)).to_have_count(0)
