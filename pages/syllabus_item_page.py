"""Shared Page Object for the simple Content Dashboard > Syllabus list pages.

Grade, Medium and Stream pages share the same UI: a card list, a "Create <Item>"
popup with a single Title field, an "Update" popup, and a two-step delete
(confirmation page + popup). Subclasses only set ITEM and PATH.
"""

import re

from playwright.sync_api import Locator, Page

from config import BASE_URL


class SyllabusItemPage:
    ITEM = ""  # e.g. "Grade" (as shown in the UI)
    PATH = ""  # e.g. "grade" (as used in the URL)

    def __init__(self, page: Page):
        self.page = page
        self.url = f"{BASE_URL}/core/{self.PATH}/list"
        self.url_pattern = re.compile(rf"/core/{self.PATH}/list$")
        self.delete_url_pattern = re.compile(rf"/core/{self.PATH}/delete\?{self.PATH}=\d+$")
        self.created_message = f"{self.ITEM} Created successfully!"
        self.updated_message = f"{self.ITEM} Updated successfully!"
        self.deleted_message = f"{self.ITEM} Deleted successfully!"

        # List page
        self.heading = page.get_by_role("heading", name=self.ITEM.upper(), level=1)
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
        self.item_titles = page.locator(".page-content").get_by_role("heading", level=3)
        self.success_alert = page.get_by_role("alert")

        # "Create <Item>" popup (the Title label is not linked to its input, so the
        # popup's only textbox is used; footer "Close" is used, not the header "x")
        self.create_dialog = page.get_by_role("dialog", name=f"Create {self.ITEM}")
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

    # ---------- Locators for a specific item ----------

    def item_title(self, name: str) -> Locator:
        return self.item_titles.filter(has_text=re.compile(rf"^{re.escape(name)}$"))

    def item_card(self, name: str) -> Locator:
        # `has=` is matched inside each card, so it must not be rooted at .page-content
        title = self.page.get_by_role("heading", level=3, name=name, exact=True)
        return self.page.locator(".card").filter(has=title)

    def is_create_title_missing(self) -> bool:
        """True when the browser's HTML5 'required' validation fails for the Title field."""
        return self.create_title_input.evaluate("el => el.validity.valueMissing")

    # ---------- Actions ----------
    # Save/Update/Delete submit a form that reloads the list (same URL), so these
    # actions wait for that navigation; otherwise the next click can hit the old page.

    def open(self) -> None:
        self.page.goto(self.url, wait_until="domcontentloaded")

    def open_add_popup(self) -> None:
        self.add_button.click()

    def close_add_popup(self) -> None:
        self.create_close_button.click()

    def save_new_item(self) -> None:
        self.create_save_button.click()

    def create_item(self, name: str) -> None:
        self.open_add_popup()
        self.create_title_input.fill(name)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.save_new_item()

    def open_edit_popup(self, name: str) -> None:
        self.item_card(name).get_by_role("button", name="Edit").click()

    def update_item_title(self, new_name: str) -> None:
        self.update_title_input.fill(new_name)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.update_save_button.click()

    def open_delete_confirmation(self, name: str) -> None:
        self.item_card(name).get_by_role("link", name="Delete").click()
        self.page.wait_for_url(self.delete_url_pattern, wait_until="domcontentloaded")

    def open_delete_confirm_popup(self) -> None:
        self.delete_page_delete_button.click()

    def accept_delete_confirm_popup(self) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.delete_confirm_button.click()

    def delete_item(self, name: str) -> None:
        self.open_delete_confirmation(name)
        self.open_delete_confirm_popup()
        self.accept_delete_confirm_popup()

    def delete_items_starting_with(self, prefix: str) -> None:
        """Clean-up helper: delete every item whose title starts with the given prefix."""
        self.open()
        matching = self.item_titles.filter(has_text=re.compile(rf"^{re.escape(prefix)}"))
        while matching.count() > 0:
            self.delete_item(matching.first.inner_text().strip())
