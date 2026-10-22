"""Shared Page Object for the course content hierarchy list pages:
Subject -> Chapter -> Topic -> Subtopic.

Each level lists the children of one parent at /core/<level>/list/<parent id> as
cards with a status badge ("Available" / "Not Available") and a "⋮" menu with
Edit / Delete. Create and Edit use popups; Delete uses a confirmation page plus a
popup. Subclasses set the level names and fill their own required create fields.
"""

import re

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config import BASE_URL


class ChangeLogPage:
    """Change Log page (/core/changelogs/<id>) opened from a card's "⋮" menu."""

    def __init__(self, page: Page, level: str):
        self.page = page
        self.heading = page.get_by_role("heading", name=f"{level} Change Log", level=3)
        # Event headings are an icon + "Created" / "Updated" (the item title is also an h5)
        self.event_titles = page.get_by_role("heading", level=5).filter(
            has_text=re.compile(r"^\W*(Created|Updated)\s*$")
        )
        self.event_data = page.locator("code")

    def event_names(self) -> list[str]:
        """Newest first, e.g. ["Updated", "Created"]."""
        return [re.sub(r"[^\w\s]", "", t).strip() for t in self.event_titles.all_text_contents()]


class SyllabusLevelPage:
    LEVEL = ""  # e.g. "Subject" (as shown in the UI)
    PATH = ""  # e.g. "subject" (as used in URLs and data-<path>-id attributes)
    CHILD_LINK = None  # link on each card that opens the next level, e.g. "Chapters"
    CREATE_REQUIRED_FIELDS = ("title",)  # `name`s of required inputs in the Create popup
    CREATE_HAS_AVAILABILITY = True  # Create popup shows a disabled "Is Available" box
    MENU_ITEMS = ()  # items in each card's "⋮" menu, in order
    TITLE_MAX_LENGTH = 220  # database limit (character varying(220)); the input has no maxlength

    AVAILABLE = "Available"
    NOT_AVAILABLE = "Not Available"
    DUPLICATE_MESSAGE = "Syllabus will be duplicated with in 5 minutes."
    COPY_SUFFIX = " - Copy"

    def __init__(self, page: Page):
        self.page = page
        self.list_url_pattern = re.compile(rf"/core/{self.PATH}/list/\d+$")
        self.delete_url_pattern = re.compile(rf"/core/{self.PATH}/delete\?{self.PATH}=\d+$")
        self.created_message = f"{self.LEVEL} Created successfully!"
        self.updated_message = f"{self.LEVEL} Updated successfully!"
        self.deleted_message = f"{self.LEVEL} Deleted successfully!"
        self.sorted_message = f"{self.LEVEL} Sorted successfully!"

        # List page
        self.heading = page.get_by_role("heading", name=f"{self.LEVEL.upper()}S", level=1)
        self.breadcrumb = page.get_by_role("navigation", name="breadcrumb")
        self.breadcrumb_home_link = self.breadcrumb.get_by_role("link").first
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
        self.sort_button = page.get_by_role("button", name="Sort", exact=True)
        # ":visible" skips the hidden copies of each card inside the Sort popup
        self.cards = page.locator(".card-body:visible").filter(has=page.locator("h3"))
        self.card_titles = self.cards.locator("h3")

        # "Create <Level>" popup (labels are not linked to inputs, so fields use their name)
        self.create_dialog = page.get_by_role("dialog", name=f"Create {self.LEVEL}")
        self.create_title_input = self.create_dialog.locator("input[name=title]")
        self.create_save_button = self.create_dialog.get_by_role("button", name="Save")
        self.create_close_button = self.create_dialog.locator(".modal-footer").get_by_role(
            "button", name="Close"
        )
        self.create_availability = self.create_dialog.locator("input[name=availability]")

        # "Update" popup (form is loaded into the popup after clicking Edit)
        self.update_dialog = page.get_by_role("dialog", name="Update")
        self.update_title_input = self.update_dialog.locator("input[name=title]")
        self.update_availability = self.update_dialog.locator("input[name=availability]")
        self.update_save_button = self.update_dialog.get_by_role("button", name="Save")
        self.update_close_button = self.update_dialog.locator(".modal-footer").get_by_role(
            "button", name="Close"
        )

        # "Sort <Level>s" popup (drag & drop cards, then "Save Changes")
        self.sort_dialog = page.get_by_role("dialog", name=f"Sort {self.LEVEL}s")
        self.sort_cards = self.sort_dialog.locator(".sort-child")
        self.sort_save_button = self.sort_dialog.get_by_role("button", name="Save Changes")
        self.sort_close_button = self.sort_dialog.get_by_role("button", name="Close")

        # "Duplicate <Level>" popup: one select per ancestor (Course, Subject, ...), last = new parent
        self.duplicate_dialog = page.get_by_role("dialog", name=f"Duplicate {self.LEVEL}")
        self.duplicate_selects = self.duplicate_dialog.locator("select")
        self.duplicate_submit_button = self.duplicate_dialog.get_by_role(
            "button", name=re.compile(r"Duplicate$")
        )

        # Delete confirmation page + final confirmation popup
        self.delete_page_heading = page.get_by_role("heading", name="Delete Multiple Objects", level=1)
        self.delete_page_delete_button = page.locator(".card-footer").get_by_role(
            "button", name="Delete All"
        )
        self.delete_page_close_button = page.locator(".card-footer").get_by_role("button", name="Close")
        self.delete_confirm_dialog = page.get_by_role(
            "dialog", name=re.compile(r"^Are you sure you want to delete")
        )
        self.delete_confirm_button = self.delete_confirm_dialog.get_by_role("button", name="Delete")
        self.delete_confirm_close_button = self.delete_confirm_dialog.locator(".modal-footer").get_by_role(
            "button", name="Close"
        )

    # ---------- Locators ----------

    def card(self, name: str) -> Locator:
        title = self.page.locator("h3", has_text=re.compile(rf"^\s*{re.escape(name)}\s*$"))
        return self.cards.filter(has=title)

    def card_status_badge(self, name: str) -> Locator:
        # First badge is availability ("Available" / "Not Available")
        return self.card(name).locator(".badge").first

    def alert(self, text: str) -> Locator:
        return self.page.get_by_role("alert").filter(has_text=text)

    def create_field(self, name: str) -> Locator:
        return self.create_dialog.locator(f"[name={name}]")

    def delete_page_item(self, name: str) -> Locator:
        return self.page.locator(".list-group-item").filter(
            has_text=re.compile(rf"^\s*{re.escape(name)}")
        )

    def item_id(self, name: str) -> str:
        return self.card(name).locator(f"[data-{self.PATH}-id]").first.get_attribute(f"data-{self.PATH}-id")

    def card_ids_and_titles(self) -> dict[str, str]:
        """{id: title} for every card on the list page."""
        pairs = self.cards.evaluate_all(
            f"cards => cards.map(c => [c.querySelector('[data-{self.PATH}-id]').dataset.{self.PATH}Id,"
            " c.querySelector('h3').textContent.trim()])"
        )
        return dict(pairs)

    def breadcrumb_link(self, text: str) -> Locator:
        return self.breadcrumb.get_by_role("link", name=text, exact=True)

    def card_menu_items(self, name: str) -> list[str]:
        """Item names in the card's "⋮" menu (icon glyphs stripped)."""
        texts = self.card(name).locator(".dropdown-menu .dropdown-item").all_text_contents()
        return [re.sub(r"[^\w\s]", "", text).strip() for text in texts]

    def sort_card_titles(self) -> list[str]:
        # Sort cards display titles in upper case via CSS; text content keeps the real title
        return [t.strip() for t in self.sort_cards.locator("h3").all_text_contents()]

    def ordered_card_titles(self) -> list[str]:
        return [t.strip() for t in self.card_titles.all_text_contents()]

    def is_create_title_missing(self) -> bool:
        return self.create_title_input.evaluate("el => el.validity.valueMissing")

    # ---------- Actions ----------
    # Save/Delete submit a form that reloads the list, so these actions wait for that
    # navigation; otherwise the next click can hit the old page.

    def open(self, parent_id: str) -> None:
        self.page.goto(f"{BASE_URL}/core/{self.PATH}/list/{parent_id}", wait_until="domcontentloaded")

    def open_add_popup(self) -> None:
        self.add_button.click()

    def close_add_popup(self) -> None:
        self.create_close_button.click()

    def save_new_item(self) -> None:
        self.create_save_button.click()

    def fill_required_create_fields(self) -> None:
        """Fill this level's required Create fields (other than Title) with valid test values."""

    def create_item(self, name: str) -> None:
        self.open_add_popup()
        self.create_title_input.fill(name)
        self.fill_required_create_fields()
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.save_new_item()

    def open_card_menu(self, name: str) -> None:
        self.card(name).locator("[data-bs-toggle=dropdown]").click()

    def open_edit_popup(self, name: str) -> None:
        self.open_card_menu(name)
        self.card(name).get_by_role("button", name="Edit").click()

    def save_edit(self) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.update_save_button.click()

    def update_title(self, name: str, new_name: str) -> None:
        self.open_edit_popup(name)
        self.update_title_input.fill(new_name)
        self.save_edit()

    def set_availability(self, name: str, available: bool) -> None:
        """Tick/untick "Is Available" in the Edit popup and save (the app may refuse it)."""
        self.open_edit_popup(name)
        # The form is fetched after the popup opens; wait until it has replaced the placeholder
        self.update_title_input.wait_for(state="visible")
        self.update_availability.set_checked(available)
        self.save_edit()

    def submit_new_item(self, name: str) -> int | None:
        """Fill the Create popup and click Save without assuming the result.

        Returns the HTTP status of the create request, or None if the browser blocked the
        submit (e.g. a required field is empty) and the popup stayed open.
        """
        self.open_add_popup()
        self.create_title_input.fill(name)
        self.fill_required_create_fields()
        return self._submit_and_get_status(self.save_new_item, f"/core/{self.PATH}/create/")

    def submit_edit_title(self, name: str, new_name: str) -> int | None:
        """Change the title in the Edit popup and click Save; returns the update request's
        HTTP status, or None if the browser blocked the submit."""
        self.open_edit_popup(name)
        self.update_title_input.fill(new_name)
        return self._submit_and_get_status(self.update_save_button.click, f"/core/{self.PATH}/update/")

    def _submit_and_get_status(self, click, url_part: str) -> int | None:
        statuses = []

        def record(response):
            if response.request.method == "POST" and url_part in response.url:
                statuses.append(response.status)

        self.page.on("response", record)
        try:
            with self.page.expect_navigation(wait_until="domcontentloaded", timeout=10_000):
                click()
        except PlaywrightTimeoutError:
            pass  # no navigation: the browser kept the popup open
        finally:
            self.page.remove_listener("response", record)
        return statuses[0] if statuses else None

    def close_edit_popup(self) -> None:
        self.update_close_button.click()

    def open_sort_popup(self) -> None:
        self.sort_button.click()

    def close_sort_popup(self) -> None:
        self.sort_close_button.click()

    def sort_move_before(self, moving: str, target: str) -> None:
        """Drag the `moving` card onto the `target` card in the Sort popup."""
        def sort_card(title):
            return self.sort_cards.filter(
                has=self.page.locator("h3", has_text=re.compile(rf"^\s*{re.escape(title)}\s*$", re.I))
            )
        sort_card(moving).drag_to(sort_card(target))

    def save_sort(self) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.sort_save_button.click()

    def duplicate_item(self, name: str, ancestor_ids: list[str]) -> None:
        """Duplicate a card under the parent chosen by `ancestor_ids` (course id, ..., parent id)."""
        self.open_card_menu(name)
        self.card(name).get_by_role("button", name="Duplicate").click()
        for index, value in enumerate(ancestor_ids):
            select = self.duplicate_selects.nth(index)
            select.locator(f"option[value='{value}']").wait_for(state="attached")
            select.select_option(str(value))
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.duplicate_submit_button.click()

    def open_change_log(self, name: str) -> None:
        self.open_card_menu(name)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.card(name).get_by_role("link", name="Change Log").click()

    def cancel_on_delete_page(self) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.delete_page_close_button.click()

    def open_children(self, name: str) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.card(name).get_by_role("link", name=self.CHILD_LINK).click()

    def open_delete_confirmation(self, name: str) -> None:
        self.open_card_menu(name)
        self.card(name).get_by_role("link", name="Delete").click()
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

    def delete_by_id(self, item_id: str) -> None:
        self.page.goto(
            f"{BASE_URL}/core/{self.PATH}/delete?{self.PATH}={item_id}", wait_until="domcontentloaded"
        )
        self.open_delete_confirm_popup()
        self.accept_delete_confirm_popup()

    def delete_items_starting_with(self, parent_id: str, prefix: str) -> None:
        """Clean-up helper: delete every item under `parent_id` whose title starts with `prefix`.
        Deletes by id, so items that share a title are handled too."""
        self.open(parent_id)
        title = self.page.locator("h3", has_text=re.compile(rf"^\s*{re.escape(prefix)}"))
        item_ids = self.cards.filter(has=title).evaluate_all(
            f"cards => cards.map(c => c.querySelector('[data-{self.PATH}-id]').dataset.{self.PATH}Id)"
        )
        for item_id in item_ids:
            self.delete_by_id(item_id)
