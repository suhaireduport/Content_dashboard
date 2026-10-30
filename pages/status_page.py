"""Page Object for the Content Dashboard > Status page (/content/status/list).

Statuses are Edureels (a video URL), Edusnaps (1 image) or Edusnap sets (2-3 images),
posted to one or more courses (or to batches of one course). Each course needs a link
choice: a chapter / topic / sub-topic, or "No link". A course holds at most 3 live
statuses; a status is live for 24h after publishing.

The Create / Edit popup is filled by the page's script and saved over AJAX: errors are
shown under each field, and the result is a toast. Course, Batch and Link pickers are a
custom search-select widget (see SearchSelect).
"""

import re
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
    NO_LINK = "No link in this course (no footer)"

    def __init__(self, page: Page):
        self.page = page

        # List page
        self.heading = page.get_by_role("heading", name="STATUS", level=1)
        self.limits_note = self.heading.locator("xpath=following-sibling::div")
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
        self.cards = page.locator("#st-results [data-post]")
        self.toasts = page.locator("#st-toasts .st-toast")

        # Create / Edit popup (no accessible name, and its labels are not linked to inputs)
        self.dialog = page.locator("#statusModal")
        self.dialog_title = self.dialog.locator("#status-modal-title")
        self.type_select = self.dialog.locator("#st-type")
        self.audience_select = self.dialog.locator("#st-audience")
        self.video_url_input = self.dialog.locator("#st-video-url")
        self.video_preview_meta = self.dialog.locator("#st-video-preview .pv-meta")
        self.video_warning = self.dialog.locator("#st-video-warn")
        self.image_input = self.dialog.locator("#st-images")
        self.image_previews = self.dialog.locator("#st-images-preview .pv-item")
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

    def image_preview_shows_whole_image(self, index: int) -> bool:
        """False when the preview frame cuts part of the image off (object-fit: cover on a
        frame whose aspect ratio differs from the image's)."""
        return self.image_previews.nth(index).locator("img").evaluate(
            """async img => {
                if (!img.complete) await new Promise(resolve => { img.onload = resolve; });
                const fit = getComputedStyle(img).objectFit;
                if (fit === 'contain' || fit === 'scale-down') return true;
                const image = img.naturalWidth / img.naturalHeight, frame = img.clientWidth / img.clientHeight;
                return Math.abs(image - frame) <= image * 0.01;
            }"""
        )

    # ---------- Actions ----------

    def open(self, query: str | None = None, course: str | None = None) -> None:
        """Open the list, optionally filtered by search text and/or a course id."""
        params = {key: value for key, value in (("q", query), ("course", course)) if value}
        self.page.goto(
            self.URL + (f"?{urlencode(params)}" if params else ""), wait_until="domcontentloaded"
        )

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

    def select_course(self, name: str) -> None:
        self.course_picker.pick(name, search=name)

    def select_batch(self, name: str) -> None:
        # Batch options are fetched after the course is chosen; typing re-filters them
        self.batch_picker.pick(name, search=name)

    def choose_link(self, course_id: str, label: str) -> None:
        picker = self.link_picker(course_id)
        # The row shows "Loading…" until the course's link options arrive
        picker.input.and_(self.page.locator(":not([placeholder='Loading…'])")).wait_for()
        picker.pick(label)

    def fill_title(self, title: str) -> None:
        self.title_input.fill(title)

    def fill_caption(self, caption: str) -> None:
        self.caption_input.fill(caption)

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
    ) -> None:
        """Open the Create popup and fill it. `courses` is {course id: name}; `links` is
        {course id: link label} and defaults to "No link" for every course ({} = no choice)."""
        self.open_add_popup()
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
        if links is None:
            links = {course_id: self.NO_LINK for course_id in courses}
        for course_id, label in links.items():
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
