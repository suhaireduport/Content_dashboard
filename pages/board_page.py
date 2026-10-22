"""Page Object for the Content Dashboard > Board page (list, create, update, delete)."""

import re

from playwright.sync_api import Locator, Page

from config import BASE_URL


class BoardPage:
    URL = f"{BASE_URL}/core/board/list"
    URL_PATTERN = re.compile(r"/core/board/list$")
    DELETE_URL_PATTERN = re.compile(r"/core/board/delete\?board=\d+$")
    CREATED_MESSAGE = "Board Created successfully!"

    def __init__(self, page: Page):
        self.page = page

        # Board list
        self.heading = page.get_by_role("heading", name="BOARD", level=1)
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
        self.board_titles = page.locator(".page-content").get_by_role("heading", level=3)
        self.success_alert = page.get_by_role("alert")

        # "Create Board" popup (the Title label is not linked to its input, so the
        # popup's only textbox is used; footer "Close" is used, not the header "x")
        self.create_dialog = page.get_by_role("dialog", name="Create Board")
        self.create_title_input = self.create_dialog.get_by_role("textbox")
        self.create_save_button = self.create_dialog.get_by_role("button", name="Save")
        self.create_close_button = self.create_dialog.locator(".modal-footer").get_by_role(
            "button", name="Close"
        )

        # "Update" popup (form is loaded into the popup after clicking Edit)
        self.update_dialog = page.get_by_role("dialog", name="Update")
        self.update_title_input = self.update_dialog.get_by_role("textbox")
        self.update_save_button = self.update_dialog.get_by_role("button", name="Save")

        # Delete confirmation page + final confirmation popup
        self.delete_page_heading = page.get_by_role("heading", name="Delete Multiple Objects", level=1)
        self.delete_page_items = page.locator(".list-group-item")
        self.delete_page_delete_button = page.locator(".card-footer").get_by_role("button", name="Delete")
        self.delete_confirm_dialog = page.get_by_role(
            "dialog", name=re.compile(r"^Are you sure you want to delete")
        )
        self.delete_confirm_button = self.delete_confirm_dialog.get_by_role("button", name="Delete")

    # ---------- Locators for a specific board ----------

    def board_title(self, name: str) -> Locator:
        return self.board_titles.filter(has_text=re.compile(rf"^{re.escape(name)}$"))

    def board_card(self, name: str) -> Locator:
        # `has=` is matched inside each card, so it must not be rooted at .page-content
        title = self.page.get_by_role("heading", level=3, name=name, exact=True)
        return self.page.locator(".card").filter(has=title)

    def is_create_title_missing(self) -> bool:
        """True when the browser's HTML5 'required' validation fails for the Title field."""
        return self.create_title_input.evaluate("el => el.validity.valueMissing")

    # ---------- Actions ----------

    def open(self) -> None:
        self.page.goto(self.URL)

    def open_add_popup(self) -> None:
        self.add_button.click()

    def close_add_popup(self) -> None:
        self.create_close_button.click()

    def save_new_board(self) -> None:
        self.create_save_button.click()

    # Save/Update/Delete submit a form that reloads the board list (same URL), so these
    # actions wait for that navigation; otherwise the next click can hit the old page.

    def create_board(self, name: str) -> None:
        self.open_add_popup()
        self.create_title_input.fill(name)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.save_new_board()

    def open_edit_popup(self, name: str) -> None:
        self.board_card(name).get_by_role("button", name="Edit").click()

    def update_board_title(self, new_name: str) -> None:
        self.update_title_input.fill(new_name)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.update_save_button.click()

    def open_delete_confirmation(self, name: str) -> None:
        self.board_card(name).get_by_role("link", name="Delete").click()
        self.page.wait_for_url(self.DELETE_URL_PATTERN, wait_until="domcontentloaded")

    def open_delete_confirm_popup(self) -> None:
        self.delete_page_delete_button.click()

    def accept_delete_confirm_popup(self) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.delete_confirm_button.click()

    def confirm_delete(self) -> None:
        self.open_delete_confirm_popup()
        self.accept_delete_confirm_popup()

    def delete_board(self, name: str) -> None:
        self.open_delete_confirmation(name)
        self.confirm_delete()
        self.page.wait_for_url(self.URL_PATTERN)

    def delete_boards_starting_with(self, prefix: str) -> None:
        """Clean-up helper: delete every board whose title starts with the given prefix."""
        self.open()
        matching = self.board_titles.filter(has_text=re.compile(rf"^{re.escape(prefix)}"))
        while matching.count() > 0:
            self.delete_board(matching.first.inner_text().strip())
