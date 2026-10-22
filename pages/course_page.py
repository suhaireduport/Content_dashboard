"""Page Object for the Content Dashboard > Course page.

The list shows every course as a card (`.course-card`) with `data-active="true|false"`.
The Active / Archived / All Courses tabs only show or hide cards in the browser,
so a card can exist in the DOM while hidden by the current tab.
"""

import re

from playwright.sync_api import Locator, Page

from config import BASE_URL


class CoursePage:
    URL = f"{BASE_URL}/core/course/list"
    URL_PATTERN = re.compile(r"/core/course/list$")
    DELETE_URL_PATTERN = re.compile(r"/core/course/delete\?course=\d+$")
    CREATED_MESSAGE = "Course Created successfully!"
    DELETED_MESSAGE = "Course Deleted successfully!"
    ACTIVE_STATUS = "Active"
    ARCHIVED_STATUS = "Archived"
    MENU_ITEMS = ("Labels", "Change Log", "Duplicate", "Edit", "Delete")
    DUPLICATE_MESSAGE = "Syllabus will be duplicated with in 5 minutes."
    COPY_SUFFIX = " - Copy"
    MENTOR_OPTION_PATTERN = re.compile(r"^.+ \(\d+\)$")  # "Name (active student count)"
    MENTORS_LOADING_TEXT = "Loading mentors..."

    def __init__(self, page: Page):
        self.page = page

        # List page
        self.heading = page.get_by_role("heading", name="COURSES", level=1)
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
        self.success_alert = page.get_by_role("alert")

        # Status tabs (each label ends with its course count, e.g. "Active 92")
        self.active_tab = page.get_by_role("tab", name=re.compile(r"^Active\b"))
        self.archived_tab = page.get_by_role("tab", name=re.compile(r"^Archived\b"))
        self.all_tab = page.get_by_role("tab", name=re.compile(r"^All Courses\b"))
        self.active_count = page.locator("#active-count")
        self.archived_count = page.locator("#archived-count")
        self.all_count = page.locator("#all-count")
        # Spinner shown while archived cards are fetched (first Archived/All visit)
        self.courses_loading = page.locator("#coursesLoading")

        # Cards (CSS locators so hidden cards are included; ":visible" = shown by current tab)
        self.course_cards = page.locator(".course-card")
        self.visible_cards = page.locator(".course-card:visible")
        self.visible_active_cards = page.locator('.course-card[data-active="true"]:visible')
        self.visible_archived_cards = page.locator('.course-card[data-active="false"]:visible')

        # "Create Course" popup (labels are not linked to inputs, so fields use their name)
        self.create_dialog = page.get_by_role("dialog", name="Create Course")
        self.create_title_input = self.create_dialog.get_by_role("textbox")
        self.create_academic_year = self.create_dialog.locator("select[name=academic_year]")
        self.create_zoho_item = self.create_dialog.locator("select[name=zoho_item_id]")
        self.create_board = self.create_dialog.locator("select[name=board]")
        self.create_grade = self.create_dialog.locator("select[name=grade]")
        self.create_medium = self.create_dialog.locator("select[name=medium]")
        self.create_stream = self.create_dialog.locator("select[name=stream]")
        self.create_is_active = self.create_dialog.locator("input[name=is_active]")
        # CSS (not role-scoped) so the mentor list can be read even while the popup is closed
        self.create_mentor_select = page.locator("#createModal #mentor-select")
        self.create_mentor_options = self.create_mentor_select.locator(
            "option:not([value='']):not(.mentor-loading-option)"
        )
        # Shown while /core/get/mentor-list loads (first time the Add popup opens)
        self.create_mentor_loading_option = self.create_mentor_select.locator(".mentor-loading-option")
        self.create_mentor_tags = page.locator("#createModal #mentor-box .badge")
        self.create_mentors_input = page.locator("#createModal #mentor-input")
        self.create_save_button = self.create_dialog.get_by_role("button", name="Save")
        self.create_close_button = self.create_dialog.locator(".modal-footer").get_by_role(
            "button", name="Close"
        )

        # "Update" popup (form is loaded into the popup after clicking Edit)
        self.update_dialog = page.get_by_role("dialog", name="Update")
        self.update_title_input = self.update_dialog.get_by_role("textbox")
        self.update_academic_year = self.update_dialog.locator("select[name=academic_year]")
        self.update_zoho_item = self.update_dialog.locator("select[name=zoho_item_id]")
        self.update_default_batch = self.update_dialog.locator("select[name=batch]")
        self.update_board = self.update_dialog.locator("select[name=board]")
        self.update_grade = self.update_dialog.locator("select[name=grade]")
        self.update_medium = self.update_dialog.locator("select[name=medium]")
        self.update_stream = self.update_dialog.locator("select[name=stream]")
        self.update_is_active = self.update_dialog.get_by_label("Is Active")
        self.update_save_button = self.update_dialog.get_by_role("button", name="Save")
        self.update_close_button = self.update_dialog.locator(".modal-footer").get_by_role(
            "button", name="Close"
        )

        # "Are you sure you want to duplicate this Course?" popup
        self.duplicate_dialog = page.get_by_role("dialog", name="Are you sure you want to duplicate this Course?")
        self.duplicate_submit_button = self.duplicate_dialog.get_by_role("button", name=re.compile(r"Duplicate$"))

        # Delete confirmation page + final confirmation popup
        self.delete_page_heading = page.get_by_role("heading", name="Delete Multiple Objects", level=1)
        self.delete_page_delete_button = page.locator(".card-footer").get_by_role(
            "button", name="Delete All"
        )
        self.delete_confirm_dialog = page.get_by_role(
            "dialog", name=re.compile(r"^Are you sure you want to delete")
        )
        self.delete_confirm_button = self.delete_confirm_dialog.get_by_role("button", name="Delete")

    # ---------- Locators for a specific course ----------

    def course_card(self, name: str) -> Locator:
        # CSS `h3` (not a role locator) so the card is found even while its tab hides it
        title = self.page.locator("h3", has_text=re.compile(rf"^{re.escape(name)}$"))
        return self.course_cards.filter(has=title)

    def course_status_badge(self, name: str) -> Locator:
        # First badge is the status (Active / Archived); second is availability
        return self.course_card(name).locator(".badge").first

    def course_detail(self, name: str, field: str) -> Locator:
        """Value cell of a card's detail row, e.g. field="Board" -> "CBSE"."""
        return self.course_card(name).locator("tr", has_text=f"{field}:").locator("td").nth(1)

    def delete_page_item(self, name: str) -> Locator:
        # The course's list item also contains a nested "Subject" list, so match its start
        return self.page.locator(".list-group-item").filter(
            has_text=re.compile(rf"^\s*{re.escape(name)}")
        )

    def course_id(self, name: str) -> str:
        return self.course_card(name).locator("[data-course-id]").first.get_attribute("data-course-id")

    def card_statuses(self) -> dict[str, bool]:
        """{course id: is active} for every card on the page (hidden or not)."""
        pairs = self.course_cards.evaluate_all(
            "cards => cards.map(c => [c.querySelector('[data-course-id]').dataset.courseId,"
            " c.dataset.active === 'true'])"
        )
        return dict(pairs)

    def card_menu_items(self, name: str) -> list[str]:
        """Item names in the card's "⋮" menu (icon glyphs stripped)."""
        texts = self.course_card(name).locator(".dropdown-menu .dropdown-item").all_text_contents()
        return [re.sub(r"[^\w\s]", "", text).strip() for text in texts]

    def card_details(self, name: str) -> dict[str, str]:
        """{"Board": ..., "Grade": ..., "Stream": ..., "Medium": ...} from the card's table."""
        rows = self.course_card(name).locator("tr").all_text_contents()
        pairs = (re.sub(r"\s+", " ", row).strip().split(":", 1) for row in rows)
        return {key.strip(): value.strip() for key, value in pairs}

    def visible_card_ids(self) -> list[str]:
        """Ids of the cards shown by the current tab, in page order."""
        return self.visible_cards.evaluate_all(
            "cards => cards.map(c => c.querySelector('[data-course-id]').dataset.courseId)"
        )

    def visible_card_statuses(self) -> list[bool]:
        """data-active of the cards shown by the current tab, in page order."""
        return self.visible_cards.evaluate_all("cards => cards.map(c => c.dataset.active === 'true')")

    def wait_for_mentors(self) -> None:
        """Wait until the mentor list has loaded (no "Loading mentors..." option left)."""
        self.create_mentor_loading_option.first.wait_for(state="detached")
        self.create_mentor_options.first.wait_for(state="attached")

    def mentor_option_labels(self) -> list[str]:
        self.wait_for_mentors()
        return [label.strip() for label in self.create_mentor_options.all_text_contents()]

    def mentor_option_ids(self) -> list[str]:
        self.wait_for_mentors()
        return self.create_mentor_options.evaluate_all("options => options.map(o => o.value)")

    def tab_count(self, count_locator: Locator) -> int:
        return int(count_locator.inner_text().strip())

    def is_create_title_missing(self) -> bool:
        """True when the browser's HTML5 'required' validation fails for the Title field."""
        return self.create_title_input.evaluate("el => el.validity.valueMissing")

    def is_default_batch_missing(self) -> bool:
        """True when the Update form's required 'Default Batch' select has no value."""
        return self.update_default_batch.evaluate("el => el.validity.valueMissing")

    # ---------- Actions ----------
    # Save/Delete submit a form that reloads the list, so these actions wait for that
    # navigation; otherwise the next click can hit the old page.

    def open(self) -> None:
        self.page.goto(self.URL, wait_until="domcontentloaded")

    def load_all_courses(self) -> None:
        """Show the All tab and wait until every course card is in the page. Archived cards
        may be lazy-loaded on the first Archived/All visit (channel dependent)."""
        self.show_all()
        self.page.wait_for_function(
            "() => document.querySelectorAll('.course-card').length >= "
            "parseInt(document.getElementById('all-count').textContent)"
        )

    def open_with_all_courses(self) -> None:
        self.open()
        self.load_all_courses()

    def show_active(self) -> None:
        self.active_tab.click()

    def show_archived(self) -> None:
        self.archived_tab.click()

    def show_all(self) -> None:
        self.all_tab.click()

    def open_add_popup(self) -> None:
        self.add_button.click()

    def close_add_popup(self) -> None:
        self.create_close_button.click()

    def save_new_course(self) -> None:
        self.create_save_button.click()

    def create_course(
        self,
        name: str,
        academic_year: str,
        zoho_item: str,
        board: str,
        grade: str,
        medium: str,
        stream: str,
        is_active: bool = True,
        mentors: tuple[str, ...] = (),
    ) -> None:
        self.open_add_popup()
        self.create_title_input.fill(name)
        self.create_academic_year.select_option(academic_year)
        self.create_zoho_item.select_option(label=zoho_item)
        self.create_board.select_option(label=board)
        self.create_grade.select_option(label=grade)
        self.create_medium.select_option(label=medium)
        self.create_stream.select_option(label=stream)
        self.create_is_active.set_checked(is_active)
        for mentor in mentors:
            self.select_mentor(mentor)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.save_new_course()

    def select_mentor(self, label: str) -> None:
        """Pick a mentor (option label "Name (count)"); it is added as a tag below the select."""
        self.create_mentor_select.select_option(label=label)

    def remove_mentor_tag(self, label: str) -> None:
        self.create_mentor_tags.filter(has_text=label).get_by_role("button", name="Remove").click()

    def open_course_menu(self, name: str) -> None:
        """Open the card's "⋮" menu (Labels, Change Log, Duplicate, Edit, Delete).
        Shows the All tab first so the card is visible whatever its status."""
        self.show_all()
        self.course_card(name).locator("[data-bs-toggle=dropdown]").click()

    def open_subjects(self, name: str) -> None:
        """Click the course card's "Subject" link (opens /core/subject/list/<course id>)."""
        self.show_all()
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.course_card(name).get_by_role("link", name="Subject").click()

    def open_labels(self, name: str) -> None:
        self.open_course_menu(name)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.course_card(name).get_by_role("link", name="Labels").click()

    def open_change_log(self, name: str) -> None:
        self.open_course_menu(name)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.course_card(name).get_by_role("link", name=re.compile(r"^Change Log")).click()

    def duplicate_course(self, name: str) -> None:
        self.open_course_menu(name)
        self.course_card(name).get_by_role("button", name=re.compile(r"^Duplicate")).click()
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.duplicate_submit_button.click()

    def open_edit_popup(self, name: str) -> None:
        self.open_course_menu(name)
        self.course_card(name).get_by_role("button", name="Edit").click()

    def change_title_and_save(self, new_name: str) -> None:
        """Fill a new title and click Save (Save may be blocked by browser validation)."""
        self.update_title_input.fill(new_name)
        self.update_save_button.click()

    def open_delete_confirmation(self, name: str) -> None:
        self.open_course_menu(name)
        self.course_card(name).get_by_role("link", name="Delete").click()
        self.page.wait_for_url(self.DELETE_URL_PATTERN, wait_until="domcontentloaded")

    def open_delete_confirm_popup(self) -> None:
        self.delete_page_delete_button.click()

    def accept_delete_confirm_popup(self) -> None:
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.delete_confirm_button.click()

    def delete_course(self, name: str) -> None:
        self.open_delete_confirmation(name)
        self.open_delete_confirm_popup()
        self.accept_delete_confirm_popup()

    def delete_courses_starting_with(self, prefix: str, attempts: int = 3) -> None:
        """Clean-up helper: delete every course whose title starts with the given prefix.

        A course delete sometimes reports success but the course is still listed on a
        later page load, so a fresh list is re-checked (up to `attempts` times).
        """
        matching = self.page.locator(".course-card h3").filter(
            has_text=re.compile(rf"^{re.escape(prefix)}")
        )
        for _ in range(attempts):
            self.open_with_all_courses()
            if matching.count() == 0:
                return
            while matching.count() > 0:
                self.delete_course(matching.first.text_content().strip())
                self.load_all_courses()


class CourseLabelsPage:
    """Course > "Labels" (/core/syllabus-label/list/<course id>)."""

    URL_PATTERN = re.compile(r"/core/syllabus-label/list/\d+$")

    def __init__(self, page: Page):
        self.page = page
        self.heading = page.get_by_role("heading", name="SYLLABUS LABELS", level=1)
        self.breadcrumb = page.get_by_role("navigation", name="breadcrumb")
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
