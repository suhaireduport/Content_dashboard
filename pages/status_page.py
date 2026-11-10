"""Page Object for the Content Dashboard > Status page (/content/status/list).

Statuses are Edureels (a video URL), Edusnaps (1 image) or Edusnap sets (2-3 images),
posted to one or more courses (or to batches of one course). Each course can link to a
chapter / topic / sub-topic; the default is "No link". A course holds at most 3 live
statuses; a status is live for 24h from its publish date and time.

The Create / Edit popup is filled by the page's script and saved over AJAX: errors are
shown under each field, and the result is a toast. Course, Batch and Link pickers are a
custom search-select widget (see SearchSelect).
"""

import base64
import re
import time
from urllib.parse import urlencode

from playwright.sync_api import Locator, Page

from config import BASE_URL


class SearchSelect:
    """The page's chip + search + dropdown picker (`.ss`)."""

    def __init__(self, root: Locator):
        self.root = root
        self.input = root.locator(".ss-input")
        self.chips = root.locator(".ss-chip > span")
        self.options = root.locator(".ss-opt")

    def option(self, label: str) -> Locator:
        return self.options.filter(has=self.root.page.get_by_text(label, exact=True))

    def pick(self, label: str, search: str | None = None) -> None:
        self.input.click()
        if search is not None:
            self.input.fill(search)
        # Options are rendered on mousedown handlers, which a click also fires
        self.option(label).click()


class StatusPage:
    URL = f"{BASE_URL}/content/status/list"
    URL_PATTERN = re.compile(r"/content/status/list")
    SAVED_MESSAGE = "Status saved."
    COURSE_FULL_MESSAGE = 'Course is full — tick "Replace oldest" to make room.'
    LIVE_LIMIT = 3
    SAVE_TIMEOUT = 60_000  # the dev server can take >30s to save

    TYPES = {"Edureel": "1", "Edusnap": "2", "Edusnap set": "3"}
    AUDIENCES = {"Course": "1", "Batch": "2"}
    NO_LINK = "No link"  # every course's default link choice
    LINK_OPTIONS_TIMEOUT = 30_000

    def __init__(self, page: Page):
        self.page = page

        # List page
        self.heading = page.get_by_role("heading", name="STATUS", level=1)
        self.limits_note = self.heading.locator("xpath=following-sibling::div")
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
        self.analytics_link = page.get_by_role("link", name=re.compile(r"^\W*Analytics$"))
        self.cards = page.locator("#st-results [data-post]")  # grid cards or list-view rows
        # ".out" = a toast fading out (an earlier message), so it is not matched
        self.toasts = page.locator("#st-toasts .st-toast:not(.out)")

        # Toolbar: search, filters, grouping and view. Each change reloads #st-results over AJAX
        # and puts the choices in the page URL.
        self.filter_form = page.locator("#st-filter-form")
        self.search_input = self.filter_form.locator("input[name=q]")
        self.type_filter = self.filter_form.locator("select[name=type]")
        self.state_filter = self.filter_form.locator("select[name=state]")
        self.course_filter = SearchSelect(page.locator("#st-course-filter"))
        self.group_select = self.filter_form.locator("select[name=group]")
        self.reset_button = self.filter_form.locator("#st-reset")
        self.grid_view_button = self.filter_form.locator("[data-view=grid]")
        self.list_view_button = self.filter_form.locator("[data-view=list]")

        # Results
        self.results = page.locator("#st-results")
        self.results_meta = self.results.locator("#st-results-meta")  # data-count = total matches
        self.empty_results = self.results.get_by_text("No status found.", exact=True)
        self.group_titles = self.results.locator(".st-group-title")
        self.list_table = self.results.locator("table")
        self.list_headers = self.list_table.locator("thead th")
        self.pager_summary = self.results.locator(".st-pager > .st-muted")
        self.pager_links = self.results.locator(".st-pager a.page-link")

        # Create / Edit popup (no accessible name, and its labels are not linked to inputs)
        self.dialog = page.locator("#statusModal")
        self.dialog_title = self.dialog.locator("#status-modal-title")
        self.publish_at_input = self.dialog.locator("#st-publish-at")  # datetime-local, defaults to now
        self.type_select = self.dialog.locator("#st-type")
        self.audience_select = self.dialog.locator("#st-audience")
        self.video_url_input = self.dialog.locator("#st-video-url")
        self.video_preview_meta = self.dialog.locator("#st-video-preview .pv-meta")
        self.video_warning = self.dialog.locator("#st-video-warn")
        self.image_input = self.dialog.locator("#st-images")
        self.image_drop_zone = self.dialog.locator("#st-drop")
        self.image_previews = self.dialog.locator("#st-images-preview .pv-item")
        self.image_positions = self.image_previews.locator(".pv-pos")
        self.image_hint = self.dialog.locator("#st-images-hint")
        self.image_warning = self.dialog.locator("#st-images-warn")
        self.course_picker = SearchSelect(self.dialog.locator("#st-course-ss"))
        self.course_hint = self.dialog.locator("#st-course-hint")
        self.batch_field = self.dialog.locator("#st-batch-wrap")
        self.batch_picker = SearchSelect(self.batch_field)
        self.links_box = self.dialog.locator("#st-links")
        self.title_input = self.dialog.locator("#st-title")
        self.caption_input = self.dialog.locator("#st-caption")
        self.replace_oldest_checkbox = self.dialog.locator("#st-replace")
        self.save_button = self.dialog.locator("#st-submit")

        # Image editor (crop / resize), opened from a preview's "✎ Edit" / "✎ Fix / crop"
        self.image_editor = self.dialog.locator("#st-editor")
        self.editor_file_name = self.image_editor.locator("#st-ed-name")
        self.editor_active_ratio = self.image_editor.locator("#st-ed-ratios button.active")
        self.editor_width_select = self.image_editor.locator("#st-ed-size")
        self.editor_output = self.image_editor.locator("#st-ed-dims")
        self.editor_apply_button = self.image_editor.locator("#st-ed-apply")
        self.editor_cancel_button = self.image_editor.locator("#st-ed-cancel")

    # ---------- Locators for a specific field / status ----------

    def field_error(self, field: str) -> Locator:
        """Inline error under a field: post_type, video_url, images, course, batch, link_<course id>."""
        return self.dialog.locator(f'.st-field[data-field="{field}"] .st-err')

    def link_row(self, course_id: str) -> Locator:
        return self.links_box.locator(f'.st-field[data-field="link_{course_id}"]')

    def link_picker(self, course_id: str) -> SearchSelect:
        return SearchSelect(self.link_row(course_id))

    def deep_link_preview(self, course_id: str) -> Locator:
        return self.link_row(course_id).locator(".st-deeplink input")

    def image_preview_meta(self, index: int) -> Locator:
        return self.image_previews.nth(index).locator(".pv-meta")

    def toast(self, text: str) -> Locator:
        return self.toasts.filter(has_text=text)

    def card(self, status_id: str) -> Locator:
        return self.page.locator(f'#st-results [data-post="{status_id}"]')

    def card_title(self, status_id: str) -> Locator:
        return self.card(status_id).locator("h6")

    def card_badges(self, status_id: str) -> Locator:
        """[type, state], e.g. ["Edureel", "Live"]."""
        return self.card(status_id).locator(".badge")

    def card_placement(self, status_id: str) -> Locator:
        """Course(s), batches and "→ <link>" line of a card."""
        return self.card(status_id).locator(".st-muted").filter(has=self.page.locator("b"))

    def image_preview_frame(self, index: int) -> Locator:
        """Phone mockup the image is previewed in, as in the app: a 9:19.5 screen the image
        fills (object-fit: cover), with shaded bands where the app's header/footer cover it."""
        return self.image_previews.nth(index).locator(".pv-frame")

    def image_preview_edit_button(self, index: int) -> Locator:
        """Opens the crop editor: "✎ Edit", or "✎ Fix / crop" for a non-9:16 image."""
        return self.image_previews.nth(index).locator("[data-a=edit]")

    def image_preview_natural_size(self, index: int) -> tuple[int, int]:
        """Pixel size of the image file shown in the preview (the file that will be uploaded)."""
        return tuple(
            self.image_preview_frame(index).locator("img").evaluate(
                """async img => {
                    if (!img.complete) await new Promise(resolve => { img.onload = resolve; });
                    return [img.naturalWidth, img.naturalHeight];
                }"""
            )
        )

    def result_count(self) -> int:
        """Total number of statuses matching the current search / filters (all pages)."""
        return int(self.results_meta.get_attribute("data-count"))

    def shown_status_ids(self) -> list[str]:
        return [row.get_attribute("data-post") for row in self.cards.all()]

    def image_preview_control(self, index: int, action: str) -> Locator:
        """Buttons under a preview: "left" (◀), "right" (▶), "del" (✕), "edit" (✎)."""
        return self.image_previews.nth(index).locator(f"[data-a={action}]")

    # ---------- Actions ----------

    def open(self, query: str | None = None, course: str | None = None) -> None:
        """Open the list, optionally filtered by search text and/or a course id."""
        params = {key: value for key, value in (("q", query), ("course", course)) if value}
        self.page.goto(
            self.URL + (f"?{urlencode(params)}" if params else ""), wait_until="domcontentloaded"
        )

    def _reload_results(self, action) -> None:
        """Run a toolbar action and wait until the list it triggers has been loaded."""
        with self.page.expect_response(
            lambda response: response.url.startswith(self.URL) and response.request.method == "GET",
            timeout=self.SAVE_TIMEOUT,
        ):
            action()
        self.results.and_(self.page.locator(":not(.st-loading)")).wait_for()

    def search(self, text: str) -> None:
        self._reload_results(lambda: self.search_input.fill(text))

    def filter_by_type(self, post_type: str) -> None:
        """"Edureel", "Edusnap", "Edusnap set", or "" for All types."""
        self._reload_results(lambda: self.type_filter.select_option(self.TYPES.get(post_type, "")))

    def filter_by_state(self, state: str) -> None:
        """"Live", "Disabled", "Expired" or "Any status"."""
        self._reload_results(lambda: self.state_filter.select_option(label=state))

    def filter_by_course(self, name: str) -> None:
        self._reload_results(lambda: self.course_filter.pick(name, search=name))

    def group_by(self, grouping: str) -> None:
        """"No grouping", "Group by month" or "Group by week"."""
        self._reload_results(lambda: self.group_select.select_option(label=grouping))

    def reset_filters(self) -> None:
        self._reload_results(self.reset_button.click)

    def switch_to_list_view(self) -> None:
        self._reload_results(self.list_view_button.click)

    def switch_to_grid_view(self) -> None:
        self._reload_results(self.grid_view_button.click)

    def open_page_number(self, number: int) -> None:
        self._reload_results(self.pager_links.filter(has_text=re.compile(rf"^{number}$")).click)

    def disable_status(self, status_id: str) -> None:
        """Click a card's "Disable" button (takes a live status off the app)."""
        with self.page.expect_response(lambda response: f"/content/status/toggle/{status_id}" in response.url):
            self.card(status_id).get_by_role("button", name="Disable").click()

    def open_add_popup(self) -> None:
        self.add_button.click()
        self.dialog.wait_for(state="visible")

    def choose_type(self, post_type: str) -> None:
        self.type_select.select_option(self.TYPES[post_type])

    def choose_audience(self, audience: str) -> None:
        self.audience_select.select_option(self.AUDIENCES[audience])

    def enter_video_url(self, url: str) -> None:
        self.video_url_input.fill(url)

    def add_images(self, files: list[dict]) -> None:
        """`files` are Playwright file payloads: {"name", "mimeType", "buffer"}."""
        self.image_input.set_input_files(files)

    def drop_images(self, files: list[dict]) -> None:
        """Drag-and-drop `files` (Playwright file payloads) onto the image drop zone."""
        payloads = [
            {"name": f["name"], "mimeType": f["mimeType"], "data": base64.b64encode(f["buffer"]).decode()}
            for f in files
        ]
        self.image_drop_zone.evaluate(
            """(zone, files) => {
                const data = new DataTransfer();
                for (const f of files) {
                    const bytes = Uint8Array.from(atob(f.data), c => c.charCodeAt(0));
                    data.items.add(new File([bytes], f.name, { type: f.mimeType }));
                }
                zone.dispatchEvent(new DragEvent('drop', { dataTransfer: data, bubbles: true, cancelable: true }));
            }""",
            payloads,
        )

    def remove_image(self, index: int) -> None:
        self.image_preview_control(index, "del").click()

    def move_image_later(self, index: int) -> None:
        self.image_preview_control(index, "right").click()

    def set_image_position(self, index: int, position: int) -> None:
        """Type a new position (1-based) into a preview's position box."""
        box = self.image_previews.nth(index).locator(".pv-ctrl input")
        box.fill(str(position))
        # Leaving the box fires "change" once, as for a user (dispatching it as well moves twice)
        box.press("Tab")

    def open_image_editor(self, index: int) -> None:
        self.image_preview_control(index, "edit").click()
        # Cropper.js is loaded on first use; the output size shows once it is ready
        self.editor_output.filter(has_text="Output").wait_for()

    def choose_crop_ratio(self, ratio: str) -> None:
        """"9:16", "9:19.5", "4:5", "1:1" or "Free"."""
        self.image_editor.locator("#st-ed-ratios").get_by_role("button", name=ratio, exact=True).click()

    def choose_output_width(self, width: str) -> None:
        """"1080", "720", "1440" or "orig"."""
        self.editor_width_select.select_option(width)

    def apply_crop(self) -> None:
        self.editor_apply_button.click()
        self.image_editor.wait_for(state="hidden")

    def cancel_crop(self) -> None:
        self.editor_cancel_button.click()
        self.image_editor.wait_for(state="hidden")

    def select_course(self, name: str) -> None:
        self.course_picker.pick(name, search=name)

    def select_batch(self, name: str) -> None:
        # Batch options are fetched after the course is chosen; typing re-filters them
        self.batch_picker.pick(name, search=name)

    def choose_link(self, course_id: str, label: str) -> None:
        picker = self.link_picker(course_id)
        option = picker.option(label)
        # The course's link options are fetched after the course is picked, with no loading
        # state shown, and an open menu is not redrawn when they arrive. An "input" event
        # redraws the menu from the options loaded so far, so redraw until the option shows.
        picker.input.click()
        deadline = time.monotonic() + self.LINK_OPTIONS_TIMEOUT / 1000
        while not option.is_visible():
            if time.monotonic() > deadline:
                raise TimeoutError(f'Link option "{label}" not shown for course {course_id}')
            picker.input.dispatch_event("input")
            self.page.wait_for_timeout(250)
        option.click()

    def fill_title(self, title: str) -> None:
        self.title_input.fill(title)

    def fill_caption(self, caption: str) -> None:
        self.caption_input.fill(caption)

    def open_edit_popup(self, status_id: str) -> None:
        """Open a card's Edit popup and wait until the saved status is loaded into it."""
        self.card(status_id).locator(".status-edit").click()
        # The title changes once the status is fetched; links/batches finish loading after it
        self.dialog_title.filter(has_text="Edit Status").wait_for()
        self.page.locator("#status-form:not(.is-loading)").wait_for()

    def save(self) -> None:
        """Click Save and wait for the result. Valid forms disable Save while the request runs;
        then the popup closes (saved) or Save is enabled again with the errors shown."""
        self.save_button.click()
        self.page.wait_for_function(
            """() => !document.getElementById('statusModal').classList.contains('show')
                     || !document.getElementById('st-submit').disabled""",
            timeout=self.SAVE_TIMEOUT,
        )

    def fill_status(
        self,
        post_type: str,
        courses: dict[str, str],
        video_url: str | None = None,
        images: list[dict] | None = None,
        links: dict[str, str] | None = None,
        audience: str = "Course",
        batches: tuple[str, ...] = (),
        title: str = "",
        caption: str = "",
        replace_oldest: bool = False,
        publish_at: str | None = None,
    ) -> None:
        """Open the Create popup and fill it. `courses` is {course id: name}; `links` is
        {course id: link label}. A course left out of `links` keeps the default, "No link".
        `publish_at` ("YYYY-MM-DDTHH:MM", local time) defaults to now; a later time schedules it."""
        self.open_add_popup()
        if publish_at is not None:
            self.publish_at_input.fill(publish_at)
        self.choose_type(post_type)
        self.choose_audience(audience)
        if video_url is not None:
            self.enter_video_url(video_url)
        if images:
            self.add_images(images)
        for name in courses.values():
            self.select_course(name)
        for name in batches:
            self.select_batch(name)
        for course_id, label in (links or {}).items():
            self.choose_link(course_id, label)
        self.fill_title(title)
        self.fill_caption(caption)
        self.replace_oldest_checkbox.set_checked(replace_oldest)

    def create_status(self, *args, **kwargs) -> None:
        """Fill the Create popup and save. The popup closes only when the save succeeds
        (the "Status saved." toast shows for 3.5s, so it is not waited for here)."""
        self.fill_status(*args, **kwargs)
        self.save()
        self.dialog.wait_for(state="hidden")
