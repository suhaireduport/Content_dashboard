"""Content Dashboard > Status (/content/status/list): Edureels, Edusnaps and Edusnap sets.

Statuses are only posted to test-only "QA Auto Course <id>" courses, and every status
posted to them is deleted after each test. Status titles start with "atmn" (STATUS_PREFIX)
to tell them apart from manually added statuses. Videos and images are generated at run
time (see tests/status_media.py).

Observed behaviour (see report):
- Video length: a video over 60s is flagged in the preview ("⚠ over 60 s") and Save is
  refused with an error under Video URL (STATUS_003; fixed on 18 Nov 2026, it used to save).
- Orientation is advisory: a non-9:16 video or image shows a warning but can still be saved.
- The image preview is a phone mockup (9:19.5 screen, filled as in the app, shaded
  header/footer bands), so edges outside the phone screen are masked in the preview only.
  Images are cropped only through the crop editor; the uploaded image is stored unchanged.
- Crop editor: the 9:19.5 ratio produces a 1079×2340 image although the editor shows
  "Output 1080×2340" (other ratios match exactly). Accepted as cosmetic (not a bug), so the
  applied size is checked to within 1px.
- When a course already has 5 live statuses, a 6th is refused unless "Replace oldest if
  course is full" is ticked; the oldest is then disabled, not deleted. Every type, an EduPoll
  or a 3-image set included, takes one slot.
- EduPolls (Status v2): the build has a "Poll kind" choice (Quiz / Opinion) and an optional
  image that the PRD does not mention, and no control to reorder options (PRD: reordering
  relabels them), so reordering is not tested.
- EduPoll image shape: the app shows a Quiz poll image at 16:10 and an Opinion poll image at
  3:2. The dashboard uses 16:10 for both kinds (preview, warning, "Crop to app size"), so the
  Opinion cases of the STATUS_022 (image) tests fail.
"""

import re
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from api.status_api import StatusApi
from pages.course_page import CoursePage
from pages.status_page import StatusPage
from tests.data import COURSE_DATA, STATUS_PREFIX
from tests.status_media import browser_image, image_size_at, png, png_size, serve_video

# Generated test media: (width, height, seconds)
VERTICAL_15S = (360, 640, 15)
VERTICAL_75S = (360, 640, 75)
LANDSCAPE_15S = (640, 360, 15)

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # "max 10 MB each"
NOT_9_16_WARNING = (
    "1 image is not 9:16 — we prefer 9:16 (e.g. 1080×1920). You can still save; it may not fill the screen."
)

# Text after "→" on a status card for each link level
CARD_LINK_TEXT = {"chapter": "Open the chapter", "topic": "Open the topic", "subtopic": "Watch the full Class"}
NO_TITLE_TEXT = "(no title)"  # card heading of a status without a title
LINK_LEVELS = ("subject", "chapter", "topic", "subtopic")


@pytest.fixture(scope="module")
def status_api(admin_page):
    return StatusApi(admin_page.request)


@pytest.fixture(scope="module")
def second_course(admin_page, qa_tree):
    """{id: name} of a second test-only course (no content), deleted after the module."""
    name = f"{qa_tree['course_name']} second"
    courses = CoursePage(admin_page)
    courses.open()
    courses.create_course(name, **COURSE_DATA)
    yield {courses.course_id(name): name}
    courses.delete_courses_starting_with(name)


@pytest.fixture
def qa_course(qa_tree, status_api):
    """{id: name} of the shared test course. Every status posted to a test course (this one
    or second_course, whose name starts with this one's) is deleted after the test."""
    yield {qa_tree["course"]: qa_tree["course_name"]}
    status_api.delete_matching(qa_tree["course_name"])


@pytest.fixture
def status_page(admin_page, qa_course):
    page_object = StatusPage(admin_page)
    page_object.open()
    return page_object


@pytest.fixture
def status_title():
    """Unique title. Starts with STATUS_PREFIX so automation statuses can be told apart
    from manually added ones in the Status list."""
    return f"{STATUS_PREFIX} QA Auto Status {uuid4().hex[:8]}"


@pytest.fixture
def video(status_page):
    """Factory: video(width, height, seconds) -> URL of a generated video served to the page."""
    urls = []

    def make(width: int, height: int, seconds: int) -> str:
        urls.append(serve_video(status_page.page, width, height, seconds))
        return urls[-1]

    yield make
    for url in urls:
        status_page.page.unroute(url)


def poll(question: str, options: tuple[str, ...] = ("Momentum", "Force", "Energy", "Power"), correct: int | None = 1) -> dict:
    """fill_status / create_status arguments for a Quiz EduPoll (b is correct by default)."""
    return {"question": question, "options": list(options), "correct": correct}


def create_polls(status_page: StatusPage, courses: dict[str, str], prefix: str, count: int) -> None:
    """Post `count` EduPolls, oldest first: "<prefix> 1" ... "<prefix> <count>"."""
    for number in range(1, count + 1):
        status_page.create_status("EduPoll", courses, **poll(f"{prefix} {number}"))


def wait_for_capacity(status_page: StatusPage, action) -> dict:
    """Run a form action (e.g. picking a course), wait for the capacity check it triggers and
    return its answer: {"max_live", "courses": [{"full", "replaces", ...}]}."""
    with status_page.page.expect_response(lambda response: "/content/status/capacity" in response.url) as info:
        action()
    return info.value.json()


def expect_nothing_saved(status_page: StatusPage, status_api: StatusApi, course_id: str) -> None:
    """The popup stays open and the (test-only) course still has no status."""
    expect(status_page.dialog).to_be_visible()
    assert status_api.count(course=course_id) == 0


def padded(image: dict, size: int) -> dict:
    """The same image file with trailing bytes added up to exactly `size` bytes (still decodable)."""
    return {**image, "buffer": image["buffer"] + bytes(size - len(image["buffer"]))}


def stored_image_sizes(status_page: StatusPage, status_api: StatusApi, status_id: str) -> list[tuple[int, int]]:
    """Sizes of a saved status's images, in the order they are shown in the app."""
    images = status_api.detail(status_id)["images"]
    return [image_size_at(status_page.page, image["url"]) for image in images]


def within_1px(pixels: str) -> str:
    """Regex matching a pixel size or one either side, e.g. "1080" -> (?:1079|1080|1081)."""
    n = int(pixels)
    return f"(?:{n - 1}|{n}|{n + 1})"


def expect_saved(status_page: StatusPage) -> None:
    # Saves made in quick succession can leave an earlier "Status saved." toast on screen
    expect(status_page.toast(StatusPage.SAVED_MESSAGE).last).to_be_visible()
    expect(status_page.dialog).to_be_hidden()


def expect_rejected(status_page: StatusPage, status_api: StatusApi, title: str) -> None:
    expect(status_page.dialog).to_be_visible()
    assert status_api.ids_matching(title) == []


# ---------- STATUS_001: Status tab ----------


def test_status_tab_is_visible(content_dashboard):
    """STATUS_001: the Status tab is shown in the Content Dashboard menu and opens the Status page."""
    expect(content_dashboard.menu_section_title("Content")).to_be_visible()
    expect(content_dashboard.menu_link("Status")).to_be_visible()

    content_dashboard.open_menu_item("Status")

    status_page = StatusPage(content_dashboard.page)
    expect(status_page.page).to_have_url(StatusPage.URL_PATTERN)
    expect(status_page.heading).to_be_visible()
    expect(status_page.limits_note).to_have_text(
        f"Max {StatusPage.LIVE_LIMIT} active per course · live for 24h from its publish date / re-enabling"
    )
    expect(status_page.add_button).to_be_visible()


# ---------- STATUS_002 - STATUS_004: Edureel video ----------


def test_create_edureel_with_vertical_video_under_60_seconds(status_page, qa_course, status_api, status_title, video):
    """STATUS_002: a vertical 9:16 video under 60s is accepted and published (Live)."""
    url = video(*VERTICAL_15S)
    status_page.fill_status("Edureel", qa_course, video_url=url, title=status_title)

    expect(status_page.video_preview_meta).to_have_text("360×640 · 9:16.0 · 15s ✓")
    expect(status_page.video_warning).to_be_hidden()

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    assert status_api.detail(status_id)["video_url"] == url
    status_page.open(status_title)
    expect(status_page.card_badges(status_id)).to_have_text(["Edureel", "Live"])


def test_edureel_over_60_seconds_is_blocked(status_page, qa_course, status_api, status_title, video):
    """STATUS_003: a video longer than 60s is flagged in the preview ("⚠ over 60 s"), cannot be
    published, and a validation message is shown."""
    status_page.fill_status("Edureel", qa_course, video_url=video(*VERTICAL_75S), title=status_title)
    expect(status_page.video_preview_meta).to_have_text("360×640 · 9:16.0 · 75s ⚠ over 60 s")

    status_page.save()

    expect(status_page.field_error("video_url")).not_to_be_empty()
    expect_rejected(status_page, status_api, status_title)


def test_edureel_orientation_is_validated_before_publishing(status_page, video):
    """STATUS_004: a landscape video is flagged before Save is clicked."""
    status_page.open_add_popup()
    status_page.choose_type("Edureel")

    status_page.enter_video_url(video(*LANDSCAPE_15S))

    expect(status_page.video_preview_meta).to_have_text("640×360 · landscape · 15s ⚠ 9:16 preferred")
    expect(status_page.video_warning).to_have_text(
        "This video is 640×360 (landscape). We prefer vertical 9:16. You can still save it."
    )


# ---------- STATUS_005 - STATUS_006: Edusnap images ----------


def test_create_edusnap_with_valid_image(status_page, qa_course, status_api, status_title):
    """STATUS_005: a 9:16 image is accepted and stored at its original size (not cropped)."""
    status_page.fill_status("Edusnap", qa_course, images=[png(1080, 1920)], title=status_title)

    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")
    expect(status_page.image_warning).to_be_hidden()

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    [image] = status_api.detail(status_id)["images"]
    assert png_size(status_page.page.request.get(image["url"]).body()) == (1080, 1920)
    status_page.open(status_title)
    expect(status_page.card_badges(status_id)).to_have_text(["Edusnap", "Live"])


def test_edusnap_preview_shows_image_in_phone_mockup(status_page):
    """STATUS_005: a 9:16 image is previewed in the phone mockup without being altered.

    The mockup is a 9:19.5 screen the image fills, as in the app, so the edges the phone
    screen does not show are masked in the preview only. The image file itself is cropped
    only if the user crops it in the editor (✎ Edit) and clicks Apply; the saved image keeps
    its size (see test_create_edusnap_with_valid_image)."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.add_images([png(1080, 1920)])

    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")
    expect(status_page.image_warning).to_be_hidden()
    frame = status_page.image_preview_frame(0)
    expect(frame).to_have_css("aspect-ratio", "9 / 19.5")
    expect(frame.locator("img")).to_have_css("object-fit", "cover")
    expect(frame.locator(".safe-top")).to_be_visible()
    expect(frame.locator(".safe-bottom")).to_be_visible()
    # No crop is suggested for a 9:16 image ("✎ Fix / crop" is shown for other ratios)
    expect(status_page.image_preview_edit_button(0)).to_have_text("✎ Edit")
    # The preview shows the original, uncropped file
    assert status_page.image_preview_natural_size(0) == (1080, 1920)


@pytest.mark.parametrize("count", [2, 3])
def test_create_edusnap_set(status_page, qa_course, status_api, status_title, count):
    """STATUS_006: 2 or 3 images are saved as one Edusnap set."""
    images = [png(1080, 1920, f"image-{number}.png") for number in range(1, count + 1)]
    status_page.fill_status("Edusnap set", qa_course, images=images, title=status_title)
    expect(status_page.image_previews).to_have_count(count)

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    detail = status_api.detail(status_id)
    assert detail["post_type"] == int(StatusPage.TYPES["Edusnap set"])
    assert len(detail["images"]) == count
    status_page.open(status_title)
    expect(status_page.card_badges(status_id)).to_have_text([f"Edusnap set · {count}", "Live"])


def test_edusnap_set_needs_two_to_three_images(status_page, qa_course, status_api, status_title):
    """STATUS_006: a set with 1 image is refused, and a 4th image is not added."""
    status_page.fill_status("Edusnap set", qa_course, images=[png(1080, 1920)], title=status_title)

    status_page.save()

    expect(status_page.field_error("images")).to_have_text("Choose 2 to 3 images.")
    expect_rejected(status_page, status_api, status_title)

    status_page.add_images([png(1080, 1920, f"image-{number}.png") for number in range(2, 5)])

    expect(status_page.image_previews).to_have_count(3)
    expect(status_page.field_error("images")).to_have_text("Only 3 images allowed per set.")


# ---------- STATUS_005 - STATUS_006: Edusnap upload, aspect ratio, crop, replace, remove ----------


def test_edusnap_without_image_is_blocked(status_page, qa_course, status_api, status_title):
    """STATUS_005: an Edusnap cannot be saved without an image."""
    status_page.fill_status("Edusnap", qa_course, title=status_title)

    status_page.save()

    expect(status_page.field_error("images")).to_have_text("Choose exactly 1 image.")
    expect_rejected(status_page, status_api, status_title)


@pytest.mark.parametrize(
    "mime_type, name", [("image/jpeg", "image.jpg"), ("image/webp", "image.webp")], ids=["jpg", "webp"]
)
def test_create_edusnap_with_jpg_or_webp_image(status_page, qa_course, status_api, status_title, mime_type, name):
    """STATUS_005: JPG and WebP images are accepted like PNG (PNG: test_create_edusnap_with_valid_image)."""
    image = browser_image(status_page.page, 1080, 1920, mime_type, name)
    status_page.fill_status("Edusnap", qa_course, images=[image], title=status_title)
    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    assert stored_image_sizes(status_page, status_api, status_id) == [(1080, 1920)]


@pytest.mark.parametrize(
    "name, mime_type",
    [("image.gif", "image/gif"), ("image.svg", "image/svg+xml"), ("notes.pdf", "application/pdf")],
    ids=["gif", "svg", "pdf"],
)
def test_unsupported_image_type_is_rejected(status_page, name, mime_type):
    """STATUS_005: only JPG, PNG and WebP files are added."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.add_images([{"name": name, "mimeType": mime_type, "buffer": b"not an accepted image"}])

    expect(status_page.field_error("images")).to_have_text(f'"{name}" is not a JPG, PNG or WebP image.')
    expect(status_page.image_previews).to_have_count(0)


def test_image_over_10_mb_is_rejected(status_page):
    """STATUS_005: an image larger than 10 MB is not added."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.add_images([padded(png(1080, 1920, "large.png"), int(10.5 * 1024 * 1024))])

    expect(status_page.field_error("images")).to_have_text('"large.png" is 10.5 MB (max 10 MB).')
    expect(status_page.image_previews).to_have_count(0)


def test_image_of_exactly_10_mb_is_accepted(status_page):
    """STATUS_005: the 10 MB limit is inclusive."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.add_images([padded(png(1080, 1920), MAX_IMAGE_BYTES)])

    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")
    expect(status_page.field_error("images")).to_be_empty()


def test_unreadable_image_is_rejected(status_page, qa_course, status_api, status_title):
    """STATUS_005: a file named and typed as PNG that is not a real image cannot be saved."""
    broken = {"name": "broken.png", "mimeType": "image/png", "buffer": b"\x89PNG\r\n\x1a\nnot an image"}
    status_page.fill_status("Edusnap", qa_course, images=[broken], title=status_title)
    expect(status_page.image_preview_meta(0)).to_have_text("✗ unreadable image")

    status_page.save()

    expect(status_page.field_error("images")).to_have_text('"broken.png" is not a valid image.')
    expect_rejected(status_page, status_api, status_title)


def test_edusnap_image_can_be_dropped(status_page):
    """STATUS_005: an image can be added by drag and drop as well as by browsing."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.drop_images([png(1080, 1920)])

    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")
    expect(status_page.field_error("images")).to_be_empty()


def test_dropping_two_images_on_edusnap_keeps_the_first(status_page):
    """STATUS_005: an Edusnap takes one image; when two are dropped only the first is kept."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.drop_images([png(1080, 1920, "first.png"), png(720, 1280, "second.png")])

    expect(status_page.field_error("images")).to_have_text("An Edusnap takes one image — using the first.")
    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")


def test_new_image_replaces_edusnap_image(status_page, qa_course, status_api, status_title):
    """STATUS_005: choosing another image replaces the Edusnap's image, and the new one is saved."""
    status_page.fill_status("Edusnap", qa_course, images=[png(1080, 1920, "first.png")], title=status_title)

    status_page.add_images([png(720, 1280, "second.png")])

    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_preview_meta(0)).to_have_text("720×1280 · 9:16.0 ✓")

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    assert stored_image_sizes(status_page, status_api, status_id) == [(720, 1280)]


def test_removed_edusnap_image_blocks_saving(status_page, qa_course, status_api, status_title):
    """STATUS_005: removing the image (✕) leaves the Edusnap without one, so Save is refused."""
    status_page.fill_status("Edusnap", qa_course, images=[png(1080, 1920)], title=status_title)

    status_page.remove_image(0)

    expect(status_page.image_previews).to_have_count(0)
    status_page.save()
    expect(status_page.field_error("images")).to_have_text("Choose exactly 1 image.")
    expect_rejected(status_page, status_api, status_title)


@pytest.mark.parametrize(
    "width, height, meta, warned",
    [
        (1080, 1900, "1080×1900 · 9:15.8 ✓", False),  # within the 5% tolerance of 9:16
        (1080, 1800, "1080×1800 · 9:15.0 ⚠ 9:16 preferred", True),
        (1080, 2340, "1080×2340 · 9:19.5 ⚠ 9:16 preferred", True),
        (1080, 1080, "1080×1080 · square ⚠ 9:16 preferred", True),
        (1920, 1080, "1920×1080 · landscape ⚠ 9:16 preferred", True),
    ],
    ids=["near-9x16", "9x15", "9x19.5", "square", "landscape"],
)
def test_edusnap_aspect_ratio_check(status_page, width, height, meta, warned):
    """STATUS_005: the image ratio is checked against 9:16 (advisory: other ratios get a warning
    and a "Fix / crop" button, not an error)."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.add_images([png(width, height)])

    expect(status_page.image_preview_meta(0)).to_have_text(meta)
    expect(status_page.image_preview_control(0, "edit")).to_have_text("✎ Fix / crop" if warned else "✎ Edit")
    if warned:
        expect(status_page.image_warning).to_have_text(NOT_9_16_WARNING)
    else:
        expect(status_page.image_warning).to_be_hidden()
    expect(status_page.field_error("images")).to_be_empty()


def test_edusnap_with_non_9_16_image_can_be_saved(status_page, qa_course, status_api, status_title):
    """STATUS_005: a non-9:16 image is only warned about; it can be saved as it is."""
    status_page.fill_status("Edusnap", qa_course, images=[png(1080, 1080)], title=status_title)
    expect(status_page.image_warning).to_have_text(NOT_9_16_WARNING)

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    assert stored_image_sizes(status_page, status_api, status_id) == [(1080, 1080)]


def test_crop_image_to_9_16_before_saving(status_page, qa_course, status_api, status_title):
    """STATUS_005: a square image cropped to 9:16 in the editor is previewed and saved at 1080×1920."""
    status_page.fill_status("Edusnap", qa_course, images=[png(1080, 1080, "square.png")], title=status_title)

    status_page.open_image_editor(0)

    expect(status_page.editor_file_name).to_have_text("square.png")
    expect(status_page.editor_active_ratio).to_have_text("9:16")
    expect(status_page.editor_output).to_have_text("Output 1080×1920 · 9:16.0 ✓")

    status_page.apply_crop()

    expect(status_page.toast("Image updated · 1080×1920")).to_be_visible()
    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")
    expect(status_page.image_warning).to_be_hidden()
    expect(status_page.image_preview_control(0, "edit")).to_have_text("✎ Edit")

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    assert stored_image_sizes(status_page, status_api, status_id) == [(1080, 1920)]


@pytest.mark.parametrize(
    "ratio, width, output",
    [
        ("9:16", "720", "Output 720×1280 · 9:16.0 ✓"),
        ("9:16", "1440", "Output 1440×2560 · 9:16.0 ✓"),
        ("9:19.5", "1080", "Output 1080×2340 · 9:19.5 ⚠ 9:16 preferred"),
        ("4:5", "1080", "Output 1080×1350 · 9:11.3 ⚠ 9:16 preferred"),
        ("1:1", "1080", "Output 1080×1080 · square ⚠ 9:16 preferred"),
    ],
    ids=["9x16-720", "9x16-1440", "9x19.5", "4x5", "1x1"],
)
def test_crop_editor_ratio_and_width(status_page, ratio, width, output):
    """STATUS_005: the editor's crop ratio and output width set the size of the applied image.

    The applied size may be 1px off the editor's "Output": 9:19.5 gives 1079×2340 because the
    ratio is stored rounded (0.4615384615). Not visible to students, so it is accepted (not a
    bug) and the size is checked to within 1px; the ratio text and warning must match exactly."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")
    status_page.add_images([png(1080, 1080)])
    status_page.open_image_editor(0)

    status_page.choose_crop_ratio(ratio)
    status_page.choose_output_width(width)

    expect(status_page.editor_output).to_have_text(output)

    status_page.apply_crop()

    width_px, height_px, rest = re.fullmatch(r"Output (\d+)×(\d+)(.*)", output).groups()
    expect(status_page.image_preview_meta(0)).to_have_text(
        re.compile(rf"^{within_1px(width_px)}×{within_1px(height_px)}{re.escape(rest)}$")
    )


def test_cancel_crop_keeps_original_image(status_page):
    """STATUS_005: cancelling the editor leaves the image as it was."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")
    status_page.add_images([png(1080, 1080)])
    status_page.open_image_editor(0)
    status_page.choose_crop_ratio("9:16")

    status_page.cancel_crop()

    expect(status_page.image_preview_meta(0)).to_have_text("1080×1080 · square ⚠ 9:16 preferred")
    expect(status_page.image_preview_control(0, "edit")).to_have_text("✎ Fix / crop")
    assert status_page.image_preview_natural_size(0) == (1080, 1080)


def test_edusnap_set_image_removal(status_page, qa_course, status_api, status_title):
    """STATUS_006: removing images from a set renumbers the rest; below 2 images Save is refused."""
    images = [png(1080, 1920, "a.png"), png(720, 1280, "b.png"), png(540, 960, "c.png")]
    status_page.fill_status("Edusnap set", qa_course, images=images, title=status_title)

    status_page.remove_image(1)

    expect(status_page.image_positions).to_have_text(["1", "2"])
    expect(status_page.image_previews.locator(".pv-meta")).to_have_text(
        ["1080×1920 · 9:16.0 ✓", "540×960 · 9:16.0 ✓"]
    )

    status_page.remove_image(0)

    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_hint).to_have_text("Add 1 more image(s) (2–3 per set).")
    status_page.save()
    expect(status_page.field_error("images")).to_have_text("Choose 2 to 3 images.")
    expect_rejected(status_page, status_api, status_title)


def test_edusnap_set_order_is_saved(status_page, qa_course, status_api, status_title):
    """STATUS_006: the order set with ◀ ▶ or the position box is the order saved (shown in the app)."""
    images = [png(1080, 1920, "a.png"), png(720, 1280, "b.png"), png(540, 960, "c.png")]
    status_page.fill_status("Edusnap set", qa_course, images=images, title=status_title)
    expect(status_page.image_hint).to_have_text(
        "Order = order shown in the app. Drag a card, use ◀ ▶, or type a position."
    )

    status_page.move_image_later(0)  # b, a, c
    status_page.set_image_position(2, 1)  # c, b, a

    expect(status_page.image_previews.locator(".pv-meta")).to_have_text(
        ["540×960 · 9:16.0 ✓", "720×1280 · 9:16.0 ✓", "1080×1920 · 9:16.0 ✓"]
    )

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    assert stored_image_sizes(status_page, status_api, status_id) == [(540, 960), (720, 1280), (1080, 1920)]


def test_switching_set_to_edusnap_with_extra_images_is_blocked(status_page, qa_course, status_api, status_title):
    """STATUS_005: images chosen for a set are kept when switching to Edusnap, which then asks to
    remove the extras."""
    images = [png(1080, 1920, f"image-{number}.png") for number in range(1, 4)]
    status_page.fill_status("Edusnap set", qa_course, images=images, title=status_title)

    status_page.choose_type("Edusnap")

    expect(status_page.image_hint).to_have_text("An Edusnap takes exactly 1 image — remove the extras.")
    status_page.save()
    expect(status_page.field_error("images")).to_have_text("Choose exactly 1 image.")
    expect_rejected(status_page, status_api, status_title)


def test_replace_image_of_saved_edusnap(status_page, qa_course, status_api, status_title):
    """STATUS_005: editing a saved Edusnap, a new image replaces the saved one."""
    status_page.create_status("Edusnap", qa_course, images=[png(1080, 1920, "first.png")], title=status_title)
    [status_id] = status_api.ids_matching(status_title)
    [saved_image] = status_api.detail(status_id)["images"]
    status_page.open(status_title)

    status_page.open_edit_popup(status_id)

    expect(status_page.type_select).to_have_value(StatusPage.TYPES["Edusnap"])
    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_preview_meta(0)).to_have_text("Saved")

    status_page.add_images([png(720, 1280, "second.png")])

    expect(status_page.image_previews).to_have_count(1)
    expect(status_page.image_preview_meta(0)).to_have_text("720×1280 · 9:16.0 ✓")

    status_page.save()

    expect_saved(status_page)
    [new_image] = status_api.detail(status_id)["images"]
    assert new_image["id"] != saved_image["id"]
    assert stored_image_sizes(status_page, status_api, status_id) == [(720, 1280)]


def test_remove_image_from_saved_edusnap_set(status_page, qa_course, status_api, status_title):
    """STATUS_006: editing a saved set of 3, a removed image is gone after saving; the others stay."""
    images = [png(1080, 1920, "a.png"), png(720, 1280, "b.png"), png(540, 960, "c.png")]
    status_page.create_status("Edusnap set", qa_course, images=images, title=status_title)
    [status_id] = status_api.ids_matching(status_title)
    first, _, third = status_api.detail(status_id)["images"]
    status_page.open(status_title)
    status_page.open_edit_popup(status_id)
    expect(status_page.image_previews.locator(".pv-meta")).to_have_text(["Saved", "Saved", "Saved"])

    status_page.remove_image(1)
    status_page.save()

    expect_saved(status_page)
    assert [image["id"] for image in status_api.detail(status_id)["images"]] == [first["id"], third["id"]]


# ---------- STATUS_007: five live statuses per course ----------


def test_sixth_live_status_replaces_oldest(status_page, qa_course, status_api, status_title, video):
    """STATUS_007 (with STATUS_016-017): every type takes one slot, so a reel, a snap, a
    3-image set and 2 polls fill a course (5/5 live). A 6th is refused until "Replace oldest"
    is ticked; then the oldest is taken off (Disabled) and the course stays at 5 live."""
    [course_name] = qa_course.values()
    status_page.create_status("Edureel", qa_course, video_url=video(*VERTICAL_15S), title=f"{status_title} 1")
    status_page.create_status("Edusnap", qa_course, images=[png(1080, 1920)], title=f"{status_title} 2")
    status_page.create_status("Edusnap set", qa_course, images=[png(1080, 1920)] * 3, title=f"{status_title} 3")
    for number in (4, 5):
        status_page.create_status("EduPoll", qa_course, **poll(f"{status_title} {number}"))
    assert status_api.course_hint(course_name) == f"{StatusPage.LIVE_LIMIT}/{StatusPage.LIVE_LIMIT} live"
    [oldest] = status_api.ids_matching(f"{status_title} 1")

    status_page.fill_status("EduPoll", qa_course, **poll(f"{status_title} 6"))
    status_page.save()

    expect(status_page.field_error("course")).to_contain_text(
        f'"{course_name}" already has 5 active status (limit 5) around that time. Oldest is #{oldest},'
    )
    expect(status_page.toast(StatusPage.COURSE_FULL_MESSAGE)).to_be_visible()
    expect(status_page.dialog).to_be_visible()
    assert len(status_api.ids_matching(course_name)) == StatusPage.LIVE_LIMIT

    status_page.replace_oldest_checkbox.check()
    status_page.save()

    expect_saved(status_page)
    assert status_api.course_hint(course_name) == "5/5 live"
    assert status_api.detail(oldest)["is_available"] is False
    newest = status_api.ids_matching(course_name)[0]
    status_page.open(course=next(iter(qa_course)))
    expect(status_page.card_badges(oldest)).to_have_text(["Edureel", "Disabled"])
    expect(status_page.card_badges(newest)).to_have_text(["EduPoll", "Live"])


# ---------- STATUS_008 - STATUS_009: audience ----------


def test_publish_status_to_multiple_courses(status_page, qa_course, second_course, status_api, status_title, video):
    """STATUS_008: a status posted to two courses is placed in exactly those courses."""
    courses = {**qa_course, **second_course}
    status_page.create_status("Edureel", courses, video_url=video(*VERTICAL_15S), title=status_title)

    [status_id] = status_api.ids_matching(status_title)
    placements = status_api.detail(status_id)["placements"]
    assert sorted(str(placement["course"]) for placement in placements) == sorted(courses)
    for course_id in courses:
        status_page.open(course=course_id)
        expect(status_page.card(status_id)).to_be_visible()
    status_page.open(status_title)
    assert sorted(status_page.card_placement(status_id).locator("b").all_inner_texts()) == sorted(courses.values())


def test_post_to_batch_needs_one_course_and_a_batch(status_page, qa_course, second_course, status_api, status_title, video):
    """STATUS_009: posting to batches allows exactly one course and requires a batch."""
    status_page.open_add_popup()
    expect(status_page.batch_field).to_be_hidden()

    status_page.choose_audience("Batch")

    expect(status_page.batch_field).to_be_visible()
    expect(status_page.course_hint).to_have_text("exactly one")

    # Picking a second course replaces the first
    [first_name], [second_name] = qa_course.values(), second_course.values()
    status_page.select_course(first_name)
    status_page.select_course(second_name)
    expect(status_page.course_picker.chips).to_have_text([second_name])

    status_page.enter_video_url(video(*VERTICAL_15S))
    status_page.fill_title(status_title)
    status_page.save()

    expect(status_page.field_error("batch")).to_have_text("Select at least one batch.")
    expect_rejected(status_page, status_api, status_title)


@pytest.mark.skip(
    reason="Blocked: posting to batches needs a batch in the test course, and a test course has no "
    "batches. Creating a batch needs a course fee, expiry date and duration (a sellable record), so it "
    "is not created automatically. Enable once a test batch strategy is agreed."
)
def test_publish_status_to_selected_batches(status_page, qa_course, status_api, status_title, video):
    """STATUS_009: a status posted to a batch is placed in that batch only. (Whether students
    outside the batch can see it is checked in the student app, not here.)"""
    [course_id] = qa_course
    batch = status_api.batches(course_id)[0]

    status_page.create_status(
        "Edureel", qa_course, video_url=video(*VERTICAL_15S), audience="Batch",
        batches=(batch["title"],), title=status_title,
    )

    [status_id] = status_api.ids_matching(status_title)
    [placement] = status_api.detail(status_id)["placements"]
    assert placement["batches"] == [batch["id"]]
    status_page.open(status_title)
    expect(status_page.card_placement(status_id)).to_contain_text(batch["title"])


# ---------- STATUS_010 - STATUS_011: course link ----------


@pytest.mark.parametrize("level", ["chapter", "topic", "subtopic"])
def test_publish_status_with_course_link(status_page, qa_course, qa_tree, status_api, status_title, video, level):
    """STATUS_010: the chosen chapter / topic / subtopic link is saved and shown on the card."""
    [course_id] = qa_course
    label = " › ".join(qa_tree[name]["name"] for name in LINK_LEVELS[: LINK_LEVELS.index(level) + 1])
    # Picked by id: the course can also list other subjects' chapters / topics / subtopics
    option = next(option for option in status_api.link_options(course_id) if str(option["id"]) == qa_tree[level]["id"])

    status_page.fill_status(
        "Edureel", qa_course, video_url=video(*VERTICAL_15S), links={course_id: label}, title=status_title
    )

    expect(status_page.link_picker(course_id).chips).to_have_text([label])
    expect(status_page.deep_link_preview(course_id)).to_have_value(option["deep_link"])

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    [placement] = status_api.detail(status_id)["placements"]
    assert str(placement["link"]) == qa_tree[level]["id"]
    status_page.open(status_title)
    expect(status_page.card_placement(status_id)).to_contain_text(
        f"→ {CARD_LINK_TEXT[level]}: {qa_tree[level]['name']}"
    )


def test_course_link_is_optional(status_page, qa_course, status_api, status_title, video):
    """STATUS_011: the link is optional; a course defaults to "No link" and saves without a choice."""
    [course_id] = qa_course
    status_page.fill_status("Edureel", qa_course, video_url=video(*VERTICAL_15S), title=status_title)

    expect(status_page.link_picker(course_id).chips).to_have_text([StatusPage.NO_LINK])
    expect(status_page.deep_link_preview(course_id)).to_be_hidden()

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(status_title)
    [placement] = status_api.detail(status_id)["placements"]
    assert not placement["link"]
    status_page.open(status_title)
    expect(status_page.card_placement(status_id)).to_contain_text("→ no link")


# ---------- STATUS_012: optional title and caption ----------


@pytest.mark.parametrize(
    "with_title, with_caption",
    [(False, False), (True, False), (False, True), (True, True)],
    ids=["no-text", "title-only", "caption-only", "title-and-caption"],
)
def test_title_and_caption_are_optional(status_page, qa_course, status_api, status_title, video, with_title, with_caption):
    """STATUS_012: a status saves with or without the optional title and caption."""
    [course_name] = qa_course.values()
    title = f"{status_title} title" if with_title else ""
    caption = f"{status_title} caption" if with_caption else ""

    status_page.fill_status("Edureel", qa_course, video_url=video(*VERTICAL_15S), title=title, caption=caption)
    status_page.save()

    expect_saved(status_page)
    # The test course holds only this test's status, so it is the only match
    [status_id] = status_api.ids_matching(course_name)
    detail = status_api.detail(status_id)
    assert (detail["title"], detail["caption"]) == (title, caption)
    status_page.open(course=next(iter(qa_course)))
    expect(status_page.card_title(status_id)).to_have_text(title or NO_TITLE_TEXT)


# ---------- STATUS_013 - STATUS_019: live limit of 5 (Status v2) ----------


def test_course_hint_counts_live_out_of_5(status_page, qa_course, status_api, status_title):
    """STATUS_013: the course picker shows the live count out of 5, e.g. "1/5 live"."""
    [course_name] = qa_course.values()
    assert status_api.course_hint(course_name) == "0/5 live"

    status_page.create_status("EduPoll", qa_course, **poll(f"{status_title} 1"))

    assert status_api.course_hint(course_name) == "1/5 live"


def test_full_course_names_status_to_be_replaced(status_page, qa_course, status_api, status_title):
    """STATUS_014 - STATUS_015: with 4 live statuses the form shows no capacity note and no
    "Replace oldest" checkbox; at 5/5 it names the status a save would replace and shows the
    checkbox. (Fails on the v2 build: the note gets the right text but stays hidden, because the
    page's CSS has "#st-capacity-note { display: none; }" and showing it only clears the inline style.)"""
    [course_name] = qa_course.values()
    create_polls(status_page, qa_course, status_title, StatusPage.LIVE_LIMIT - 1)

    status_page.open_add_popup()
    wait_for_capacity(status_page, lambda: status_page.select_course(course_name))

    expect(status_page.capacity_note).to_be_hidden()
    expect(status_page.replace_oldest_checkbox).to_be_hidden()

    status_page.open()
    status_page.create_status("EduPoll", qa_course, **poll(f"{status_title} {StatusPage.LIVE_LIMIT}"))
    status_page.open_add_popup()
    wait_for_capacity(status_page, lambda: status_page.select_course(course_name))

    expect(status_page.capacity_note).to_be_visible()
    expect(status_page.capacity_note).to_contain_text(
        f'{course_name} is full (5/5): will replace "{status_title} 1" (EduPoll, expires '
    )
    expect(status_page.replace_oldest_checkbox).to_be_visible()
    expect(status_page.replace_oldest_checkbox).not_to_be_checked()


def test_reenable_in_full_course_asks_before_replacing(status_page, qa_course, status_api, status_title):
    """STATUS_018: re-enabling a disabled status in a full course asks first, like Save.
    Cancel changes nothing; "Replace oldest" puts it live and disables the oldest live one."""
    [course_id], [course_name] = qa_course, qa_course.values()
    status_page.create_status("EduPoll", qa_course, **poll(f"{status_title} off"))
    [disabled] = status_api.ids_matching(course_name)
    status_page.open(course=course_id)
    status_page.disable_status(disabled)
    create_polls(status_page, qa_course, status_title, StatusPage.LIVE_LIMIT)
    [oldest_live] = status_api.ids_matching(f"{status_title} 1")
    assert status_api.course_hint(course_name) == "5/5 live"

    status_page.open(course=course_id)
    status_page.click_enable(disabled)

    expect(status_page.confirm_dialog).to_be_visible()
    expect(status_page.confirm_title).to_have_text("Course is full")
    expect(status_page.confirm_body).to_contain_text("Replace the oldest live status?")

    status_page.dismiss_confirm()

    assert status_api.detail(disabled)["is_available"] is False
    assert status_api.detail(oldest_live)["is_available"] is True

    status_page.click_enable(disabled)
    status_page.confirm()

    assert status_api.detail(disabled)["is_available"] is True
    assert status_api.detail(oldest_live)["is_available"] is False
    assert status_api.course_hint(course_name) == "5/5 live"


def test_capacity_note_lists_only_full_courses(status_page, qa_course, second_course, status_api, status_title):
    """STATUS_019: posting to a full course and a course with room names only the full one."""
    [course_name], [second_name] = qa_course.values(), second_course.values()
    create_polls(status_page, qa_course, status_title, StatusPage.LIVE_LIMIT)

    status_page.open_add_popup()
    status_page.select_course(course_name)
    wait_for_capacity(status_page, lambda: status_page.select_course(second_name))

    # Text only: the note's visibility is checked by STATUS_014
    expect(status_page.capacity_note.locator("div")).to_have_count(1)
    expect(status_page.capacity_note).to_contain_text(f"{course_name} is full (5/5)")
    expect(status_page.capacity_note).not_to_contain_text(second_name)
    expect(status_page.replace_oldest_checkbox).to_be_visible()


@pytest.mark.skip(
    reason="Needs the student feed (GET /api/v3/status/?course=<id>) and a student test account, "
    "which this suite does not have."
)
def test_feed_returns_max_live():
    """STATUS_020: the student feed carries max_live: 5, so the app never hard-codes the limit."""


# ---------- STATUS_021 - STATUS_039: EduPolls (Status v2) ----------

POLL_ERRORS = {
    "poll_question": "Write the question.",
    "poll_options_empty": "Fill in every option or remove the empty one.",
    "poll_options_same": "Two options are the same.",
    "poll_correct": "Pick the correct answer.",
}


def test_edupoll_shows_poll_fields_only(status_page):
    """STATUS_021: the EduPoll type shows Poll kind, Question and 2 option rows (a, b) with a
    correct-answer radio each, and hides title, caption, video, share and save."""
    status_page.open_add_popup()

    status_page.choose_type("EduPoll")

    expect(status_page.poll_fields).to_be_visible()
    expect(status_page.poll_kind_select).to_have_value("quiz")
    expect(status_page.poll_keys).to_have_text(["a", "b"])
    expect(status_page.poll_option_inputs).to_have_count(2)
    expect(status_page.poll_correct_radios).to_have_count(2)
    for radio in status_page.poll_correct_radios.all():
        expect(radio).to_be_visible()
    expect(status_page.poll_question_count).to_have_text(question_count(0, 0))
    expect(status_page.poll_preview_question).to_have_text("Your question appears here")
    for hidden in (
        status_page.title_input,
        status_page.caption_input,
        status_page.video_url_input,
        status_page.share_checkbox,
        status_page.save_checkbox,
    ):
        expect(hidden).to_be_hidden()

    status_page.choose_type("Edureel")

    expect(status_page.poll_fields).to_be_hidden()
    expect(status_page.title_input).to_be_visible()


@pytest.mark.parametrize("count", [2, 5])
def test_create_edupoll(status_page, qa_course, status_api, status_title, count):
    """STATUS_022 / STATUS_035: a Quiz poll with 2 or 5 options is saved with keys a-e and one
    correct option; the card shows the question and "EduPoll · <n> options"."""
    [course_id], [course_name] = qa_course, qa_course.values()
    options = ("Momentum", "Force", "Energy", "Power", "Pressure")[:count]
    question = f"{status_title} Which quantity has the dimensions [M L T⁻²]?"

    status_page.fill_status("EduPoll", qa_course, **poll(question, options))

    expect(status_page.poll_keys).to_have_text(list("abcde"[:count]))
    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(course_name)
    detail = status_api.detail(status_id)
    assert detail["post_type"] == 4
    assert detail["poll_kind"] == "quiz"
    assert detail["poll_question"] == question
    assert detail["poll_options"] == [
        {"key": key, "text": text, "is_correct": index == 1}
        for index, (key, text) in enumerate(zip("abcde", options))
    ]
    assert (detail["title"], detail["caption"]) == ("", "")
    assert (detail["allow_save"], detail["allow_share"]) == (False, False)
    assert detail["locked"] is False
    status_page.open(course=course_id)
    expect(status_page.card_badges(status_id)).to_have_text(["EduPoll", "Live"])
    expect(status_page.card_title(status_id)).to_have_text(question)
    expect(status_page.card(status_id)).to_contain_text(f"EduPoll · {count} options")


def test_create_opinion_poll_without_correct_answer(status_page, qa_course, status_api, status_title):
    """STATUS_022 (Opinion): an Opinion poll hides the correct-answer radios and saves with no
    correct option. (Opinion polls are in the build but not in the PRD.)"""
    [course_name] = qa_course.values()
    status_page.fill_status(
        "EduPoll", qa_course, poll_kind="Opinion", **poll(f"{status_title} opinion", ("Yes", "No"), correct=None)
    )

    for radio in status_page.poll_correct_radios.all():
        expect(radio).to_be_hidden()
    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(course_name)
    detail = status_api.detail(status_id)
    assert detail["poll_kind"] == "opinion"
    assert [option["is_correct"] for option in detail["poll_options"]] == [False, False]


def test_create_edupoll_with_optional_image(status_page, qa_course, status_api, status_title):
    """STATUS_022 (image): an EduPoll can carry one image shown above the question."""
    [course_name] = qa_course.values()
    status_page.fill_status("EduPoll", qa_course, images=[png(1080, 1920)], **poll(f"{status_title} image"))
    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(course_name)
    assert len(status_api.detail(status_id)["images"]) == 1


# Shape of the poll image card in the app, per poll kind:
# (ratio, CSS aspect-ratio of the preview, an image of that shape, a square 1080px image cropped to it)
POLL_IMAGE_SHAPES = {
    "Quiz": ("16:10", "16 / 10", (1600, 1000), (1080, 675)),
    "Opinion": ("3:2", "3 / 2", (1500, 1000), (1080, 720)),
}

# Known bug (Low): the poll image is set up as 16:10 for both kinds; the app shows an Opinion
# poll image at 3:2. strict: once it is fixed the test XPASSes and fails the run, so remove
# this mark then.
OPINION_SHAPE_BUG = pytest.mark.xfail(
    reason="Known bug: Opinion poll image uses 16:10 instead of the app's 3:2",
    raises=AssertionError,
    strict=True,
)
POLL_KINDS = ["Quiz", pytest.param("Opinion", marks=OPINION_SHAPE_BUG)]


def not_poll_shape_warning(ratio: str) -> str:
    return (f"This image is not {ratio} — the app shows a poll image at about that shape. "
            "Use “✎ Crop to app size” to fit it. You can still save.")


@pytest.mark.parametrize("kind", POLL_KINDS)
def test_edupoll_image_preview_matches_app_shape(status_page, kind):
    """STATUS_022 (image): the poll image is previewed in the app's card shape for the poll kind
    (Quiz 16:10, Opinion 3:2), and an image of that shape is accepted without a warning.

    Observed: [Opinion] fails. The poll image is set up as 16:10 for both kinds; the app shows an
    Opinion poll image at 3:2."""
    ratio, css_ratio, (width, height), _ = POLL_IMAGE_SHAPES[kind]
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")
    status_page.choose_poll_kind(kind)

    status_page.add_images([png(width, height)])

    expect(status_page.poll_image_note).to_contain_text(f"about {ratio}")
    expect(status_page.image_preview_frame(0)).to_have_css("aspect-ratio", css_ratio)
    expect(status_page.image_preview_meta(0)).to_have_text(f"{width}×{height} · landscape ✓")
    expect(status_page.image_preview_control(0, "edit")).to_have_text("✎ Edit")
    expect(status_page.image_warning).to_be_hidden()


@pytest.mark.parametrize("kind", POLL_KINDS)
def test_edupoll_vertical_image_is_warned(status_page, kind):
    """STATUS_022 (image): a 9:16 image on a poll is flagged against the poll kind's shape and
    offered "Crop to app size" (advisory: it can still be saved).

    Observed: [Opinion] fails. The poll image is set up as 16:10 for both kinds; the app shows an
    Opinion poll image at 3:2."""
    ratio = POLL_IMAGE_SHAPES[kind][0]
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")
    status_page.choose_poll_kind(kind)

    status_page.add_images([png(1080, 1920)])

    expect(status_page.image_preview_meta(0)).to_have_text(f"1080×1920 · 9:16.0 ⚠ {ratio} matches the app")
    expect(status_page.image_preview_control(0, "edit")).to_have_text("✎ Crop to app size")
    expect(status_page.image_warning).to_have_text(not_poll_shape_warning(ratio))
    expect(status_page.field_error("images")).to_be_empty()


@pytest.mark.parametrize("kind", POLL_KINDS)
def test_edupoll_crop_image_to_app_size(status_page, qa_course, status_api, status_title, kind):
    """STATUS_022 (image): "Crop to app size" starts at the poll kind's shape, and the cropped
    image is saved at that shape (a square 1080px image: Quiz 1080×675, Opinion 1080×720).

    Observed: [Opinion] fails. The poll image is set up as 16:10 for both kinds; the app shows an
    Opinion poll image at 3:2."""
    [course_name] = qa_course.values()
    ratio, _, _, (width, height) = POLL_IMAGE_SHAPES[kind]
    status_page.fill_status(
        "EduPoll", qa_course, images=[png(1080, 1080)], poll_kind=kind,
        **poll(f"{status_title} {kind} image", correct=1 if kind == "Quiz" else None),
    )

    status_page.open_image_editor(0)

    expect(status_page.editor_active_ratio).to_have_text(ratio)
    expect(status_page.editor_output).to_have_text(f"Output {width}×{height} · landscape ✓")

    status_page.apply_crop()

    expect(status_page.toast(f"Image updated · {width}×{height}")).to_be_visible()
    expect(status_page.image_preview_meta(0)).to_have_text(f"{width}×{height} · landscape ✓")
    expect(status_page.image_warning).to_be_hidden()

    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(course_name)
    assert stored_image_sizes(status_page, status_api, status_id) == [(width, height)]


@OPINION_SHAPE_BUG
def test_edupoll_image_shape_follows_poll_kind(status_page):
    """STATUS_022 (image): changing the poll kind after adding an image switches the preview to
    that kind's shape.

    Observed: fails. The preview stays 16:10 when the kind is changed to Opinion (expected 3:2)."""
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")
    status_page.add_images([png(1600, 1000)])

    for kind in ("Opinion", "Quiz"):
        ratio, css_ratio, _, _ = POLL_IMAGE_SHAPES[kind]
        status_page.choose_poll_kind(kind)
        expect(status_page.poll_image_note).to_contain_text(f"about {ratio}")
        expect(status_page.image_preview_frame(0)).to_have_css("aspect-ratio", css_ratio)


def test_add_and_remove_option_limits(status_page):
    """STATUS_023: "+ Add option" adds rows up to 5 and then disappears; rows can be removed
    only while there are more than 2."""
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")
    expect(status_page.poll_remove_buttons).to_have_count(0)

    for count in range(3, 6):
        status_page.add_poll_option()
        expect(status_page.poll_rows).to_have_count(count)

    expect(status_page.poll_keys).to_have_text(list("abcde"))
    expect(status_page.poll_add_button).to_be_hidden()
    expect(status_page.poll_remove_buttons).to_have_count(5)

    for count in range(4, 1, -1):
        status_page.remove_poll_option(0)
        expect(status_page.poll_rows).to_have_count(count)
        expect(status_page.poll_add_button).to_be_visible()

    expect(status_page.poll_remove_buttons).to_have_count(0)


@pytest.mark.parametrize(
    "question, options, correct, field, message",
    [
        ("", ("A", "B"), 0, "poll_question", POLL_ERRORS["poll_question"]),
        ("   ", ("A", "B"), 0, "poll_question", POLL_ERRORS["poll_question"]),
        ("Q", ("A", ""), 0, "poll_options", POLL_ERRORS["poll_options_empty"]),
        ("Q", ("A", "   "), 0, "poll_options", POLL_ERRORS["poll_options_empty"]),
        ("Q", ("Force", " force "), 0, "poll_options", POLL_ERRORS["poll_options_same"]),
        ("Q", ("A", "B"), None, "poll_correct", POLL_ERRORS["poll_correct"]),
    ],
    ids=["no-question", "blank-question", "empty-option", "blank-option", "same-options", "no-correct-answer"],
)
def test_edupoll_validation_blocks_save(status_page, qa_course, status_api, question, options, correct, field, message):
    """STATUS_024: Save is blocked with the error beside the field for a missing question, an
    empty option, two options that are the same (trimmed, ignoring case) or no correct answer."""
    status_page.fill_status("EduPoll", qa_course, question=question, options=list(options), correct=correct)
    status_page.save()

    expect(status_page.field_error(field)).to_have_text(message)
    expect_nothing_saved(status_page, status_api, next(iter(qa_course)))


def test_edupoll_text_length_limits(status_page):
    """STATUS_025: the question takes at most 250 characters and each option at most 80."""
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")

    status_page.fill_poll_question("q" * (StatusPage.POLL_QUESTION_MAX + 10))
    status_page.poll_option_inputs.first.fill("o" * (StatusPage.POLL_OPTION_MAX + 10))

    expect(status_page.poll_question_input).to_have_value("q" * StatusPage.POLL_QUESTION_MAX)
    expect(status_page.poll_question_count).to_have_text(question_count(StatusPage.POLL_QUESTION_MAX, 1))
    expect(status_page.poll_option_inputs.first).to_have_value("o" * StatusPage.POLL_OPTION_MAX)


def test_edupoll_question_line_limit(status_page):
    """STATUS_025: the question takes at most 5 lines - pasted text keeps only the first 5 lines,
    Enter does nothing on the 5th line, and blank lines are not counted."""
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")
    max_lines = StatusPage.POLL_QUESTION_MAX_LINES
    lines = [f"line{number}" for number in range(1, max_lines + 3)]
    kept = "\n".join(lines[:max_lines])

    status_page.fill_poll_question("\n".join(lines))
    expect(status_page.poll_question_input).to_have_value(kept)
    expect(status_page.poll_question_count).to_have_text(question_count(len(kept), max_lines))

    status_page.fill_poll_question("")
    status_page.poll_question_input.click()
    for number, line in enumerate(lines, start=1):
        status_page.page.keyboard.type(line)
        if number < len(lines):
            status_page.page.keyboard.press("Enter")
    typed = kept + "".join(lines[max_lines:])  # the extra lines run on in the 5th line
    expect(status_page.poll_question_input).to_have_value(typed)
    expect(status_page.poll_question_count).to_have_text(question_count(len(typed), max_lines))

    status_page.fill_poll_question("first\n\n\nlast")
    expect(status_page.poll_question_count).to_have_text(question_count(len("first\n\n\nlast"), 2))


def question_count(characters: int, lines: int) -> str:
    """The poll question counter text, e.g. "0/250 · 0/5 lines"."""
    return (f"{characters}/{StatusPage.POLL_QUESTION_MAX} · "
            f"{lines}/{StatusPage.POLL_QUESTION_MAX_LINES} lines")


def text_of_length(seed: str, length: int) -> str:
    """`seed` repeated to exactly `length` characters, with no space at either end."""
    text = (seed * (length // len(seed) + 1))[:length].strip()
    return text + "." * (length - len(text))


MALAYALAM = "ഒരു വസ്തുവിന്റെ ത്വരണം കണ്ടുപിടിക്കുക "


@pytest.mark.parametrize("language", ["malayalam", "unicode-formula"])
def test_edupoll_text_is_saved_unchanged(status_page, qa_course, status_api, language):
    """STATUS_026 - STATUS_027: a 250-character Malayalam question with 80-character Malayalam
    options (limits counted in characters, not bytes) and Unicode formulas are saved as typed."""
    [course_id], [course_name] = qa_course, qa_course.values()
    if language == "malayalam":
        question = text_of_length(f"{STATUS_PREFIX} {MALAYALAM}", StatusPage.POLL_QUESTION_MAX)
        options = [text_of_length(f"({number}) {MALAYALAM}", StatusPage.POLL_OPTION_MAX) for number in range(1, 6)]
    else:
        question = f"{STATUS_PREFIX} Which has the dimensions [M L T⁻²] and units kg·m·s⁻²?"
        options = ["[M L² T⁻²]", "[M L T⁻²]", "[M⁰ L T⁻¹]", "√(2gh) ≈ v₀"]

    status_page.fill_status("EduPoll", qa_course, **poll(question, tuple(options)))
    expect(status_page.poll_question_input).to_have_value(question)
    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(course_name)
    detail = status_api.detail(status_id)
    assert detail["poll_question"] == question
    assert [option["text"] for option in detail["poll_options"]] == options
    status_page.open(course=course_id)
    expect(status_page.card_title(status_id)).to_have_text(question)


def test_removing_middle_option_relabels(status_page):
    """STATUS_028 / STATUS_030: labels follow position, so removing (b) of 5 relabels the rest
    a-d, and the correct answer stays on its option."""
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")
    status_page.fill_poll_question("Q")
    status_page.fill_poll_options(["A", "B", "C", "D", "E"])
    status_page.mark_correct(3)  # "D"

    status_page.remove_poll_option(1)

    expect(status_page.poll_keys).to_have_text(["a", "b", "c", "d"])
    assert [box.input_value() for box in status_page.poll_option_inputs.all()] == ["A", "C", "D", "E"]
    expect(status_page.poll_correct_radios.nth(2)).to_be_checked()
    expect(status_page.poll_preview_options).to_have_text(["(a) A", "(b) C", "(c) D ✓", "(d) E"])


def test_removing_correct_option_clears_choice(status_page, qa_course, status_api, status_title):
    """STATUS_031: removing the correct option clears the choice, and Save asks for a new one."""
    status_page.fill_status("EduPoll", qa_course, **poll(f"{status_title} removed", ("A", "B", "C"), correct=1))

    status_page.remove_poll_option(1)

    for radio in status_page.poll_correct_radios.all():
        expect(radio).not_to_be_checked()
    status_page.save()

    expect(status_page.field_error("poll_correct")).to_have_text(POLL_ERRORS["poll_correct"])
    expect_nothing_saved(status_page, status_api, next(iter(qa_course)))


def test_edupoll_preview_and_long_text_warning(status_page):
    """STATUS_032: the phone preview shows the question and labelled options with a tick on the
    correct one, and warns when the text is long (question over 180 or an option over 60 chars)."""
    status_page.open_add_popup()
    status_page.choose_type("EduPoll")
    status_page.fill_poll_question("Which is a vector?")
    status_page.fill_poll_options(["Mass", "Force"])
    status_page.mark_correct(1)

    expect(status_page.poll_preview_question).to_have_text("Which is a vector?")
    expect(status_page.poll_preview_options).to_have_text(["(a) Mass", "(b) Force ✓"])
    expect(status_page.poll_overflow_warning).to_be_hidden()

    status_page.fill_poll_question("q" * 181)
    expect(status_page.poll_overflow_warning).to_have_text(StatusPage.POLL_LONG_TEXT_WARNING)

    status_page.fill_poll_question("q" * 180)
    expect(status_page.poll_overflow_warning).to_be_hidden()

    status_page.poll_option_inputs.first.fill("o" * 61)
    expect(status_page.poll_overflow_warning).to_be_visible()


def test_edupoll_with_course_link(status_page, qa_course, qa_tree, status_api, status_title):
    """STATUS_033: an EduPoll takes the same per-course link as the other types."""
    [course_id], [course_name] = qa_course, qa_course.values()
    label = " › ".join(qa_tree[name]["name"] for name in LINK_LEVELS[:2])
    status_page.fill_status("EduPoll", qa_course, links={course_id: label}, **poll(f"{status_title} link"))
    status_page.save()

    expect_saved(status_page)
    [status_id] = status_api.ids_matching(course_name)
    [placement] = status_api.detail(status_id)["placements"]
    assert str(placement["link"]) == qa_tree["chapter"]["id"]


def test_search_and_type_filter_find_edupoll(status_page, qa_course, status_api, status_title):
    """STATUS_036: the list search finds a poll by its question, and the type filter
    "EduPoll" shows it while "Edureel" does not."""
    [course_id], [course_name] = qa_course, qa_course.values()
    question = f"{status_title} searchable question"
    status_page.create_status("EduPoll", qa_course, **poll(question))
    [status_id] = status_api.ids_matching(course_name)

    status_page.open(course=course_id)
    status_page.filter_by_type("EduPoll")
    expect_shown(status_page, status_id)
    status_page.filter_by_type("Edureel")
    expect(status_page.empty_results).to_be_visible()

    status_page.open()
    status_page.search(question)
    expect_shown(status_page, status_id)


def test_unanswered_edupoll_can_be_edited(status_page, qa_course, status_api, status_title):
    """STATUS_037: before anyone answers, the question, options and correct answer can be changed."""
    [course_id], [course_name] = qa_course, qa_course.values()
    status_page.create_status("EduPoll", qa_course, **poll(f"{status_title} before", ("A", "B")))
    [status_id] = status_api.ids_matching(course_name)
    status_page.open(course=course_id)

    status_page.open_edit_popup(status_id)

    expect(status_page.poll_locked_note).to_be_hidden()
    expect(status_page.poll_question_input).to_have_value(f"{status_title} before")
    expect(status_page.poll_correct_radios.nth(1)).to_be_checked()
    status_page.fill_poll_question(f"{status_title} after")
    status_page.fill_poll_options(["A", "B", "C"])
    status_page.mark_correct(2)
    status_page.save()

    expect_saved(status_page)
    detail = status_api.detail(status_id)
    assert detail["poll_question"] == f"{status_title} after"
    assert [(option["text"], option["is_correct"]) for option in detail["poll_options"]] == [
        ("A", False), ("B", False), ("C", True)
    ]


@pytest.mark.skip(
    reason="Needs a student answer (POST /api/v3/status/{id}/answer) and a student test account, "
    "which this suite does not have."
)
def test_answered_edupoll_is_locked():
    """STATUS_038: once one student has answered, the question, options and correct answer are
    read-only, the "already answered" note shows and the type cannot change."""


# ---------- Status list: search, filters, grouping, view mode, paging ----------


@pytest.fixture(scope="module")
def listed_statuses(admin_page, status_api):
    """A test-only "QA Auto Course <id> list" with 3 statuses: a live Edureel with a caption,
    a live Edusnap and a disabled Edureel. A separate course, so the per-test clean-up of the
    shared QA course does not delete them. Statuses and course are deleted after the module."""
    tag = uuid4().hex[:8]
    course_name = f"QA Auto Course {tag} list"
    title = f"{STATUS_PREFIX} QA Auto Status {tag}"
    courses = CoursePage(admin_page)
    status_page = StatusPage(admin_page)
    try:
        courses.open()
        courses.create_course(course_name, **COURSE_DATA)
        course = {courses.course_id(course_name): course_name}
        status_page.open()
        url = serve_video(admin_page, *VERTICAL_15S)
        caption = f"caption {tag}"
        status_page.create_status("Edureel", course, video_url=url, title=f"{title} reel", caption=caption)
        status_page.create_status("Edusnap", course, images=[png(1080, 1920)], title=f"{title} snap")
        status_page.create_status("Edureel", course, video_url=url, title=f"{title} off")
        admin_page.unroute(url)
        ids = {name: status_api.ids_matching(f"{title} {name}")[0] for name in ("reel", "snap", "off")}
        status_page.open(f"{title} off")
        status_page.disable_status(ids["off"])
        yield {"title": title, "caption": caption, "course_name": course_name, "ids": ids}
    finally:
        status_api.delete_matching(course_name)
        courses.delete_courses_starting_with(course_name)


@pytest.fixture
def status_list(admin_page, listed_statuses):
    page_object = StatusPage(admin_page)
    page_object.open()
    return page_object


def expect_shown(status_list: StatusPage, *status_ids: str) -> None:
    """The list shows exactly these statuses."""
    expect(status_list.cards).to_have_count(len(status_ids))
    assert sorted(status_list.shown_status_ids()) == sorted(status_ids)
    assert status_list.result_count() == len(status_ids)


@pytest.mark.parametrize("field", ["title", "caption", "course"])
def test_search_by_title_caption_and_course(status_list, listed_statuses, field):
    """Status list: the search box finds statuses by title, caption or course name."""
    ids = listed_statuses["ids"]
    text, expected = {
        "title": (f"{listed_statuses['title']} snap", [ids["snap"]]),
        "caption": (listed_statuses["caption"], [ids["reel"]]),
        "course": (listed_statuses["course_name"], list(ids.values())),
    }[field]

    status_list.search(text)

    expect_shown(status_list, *expected)
    expect(status_list.page).to_have_url(re.compile(r"[?&]q="))


@pytest.mark.parametrize(
    "text", [f"{STATUS_PREFIX}-no-such-status-{uuid4().hex[:8]}", "%_'\"<b>\\"], ids=["unknown", "special-characters"]
)
def test_search_without_match_shows_empty_state(status_list, text):
    """Status list: a search that matches nothing shows "No status found." (special characters
    are searched as text, not as wildcards)."""
    status_list.search(text)

    expect(status_list.empty_results).to_be_visible()
    expect(status_list.cards).to_have_count(0)
    assert status_list.result_count() == 0


@pytest.mark.parametrize(
    "post_type, expected",
    [("Edureel", ["reel", "off"]), ("Edusnap", ["snap"]), ("Edusnap set", []), ("EduPoll", [])],
    ids=["edureel", "edusnap", "edusnap-set", "edupoll"],
)
def test_filter_by_type(status_list, listed_statuses, post_type, expected):
    """Status list: the type filter shows only statuses of that type."""
    status_list.search(listed_statuses["title"])

    status_list.filter_by_type(post_type)

    expect_shown(status_list, *(listed_statuses["ids"][name] for name in expected))
    if not expected:
        expect(status_list.empty_results).to_be_visible()


@pytest.mark.parametrize(
    "state, expected", [("Live", ["reel", "snap"]), ("Disabled", ["off"]), ("Expired", [])],
    ids=["live", "disabled", "expired"],
)
def test_filter_by_state(status_list, listed_statuses, state, expected):
    """Status list: the status filter shows only Live / Disabled / Expired statuses."""
    status_list.search(listed_statuses["title"])

    status_list.filter_by_state(state)

    expect_shown(status_list, *(listed_statuses["ids"][name] for name in expected))
    for status_id in status_list.shown_status_ids():
        expect(status_list.card_badges(status_id).last).to_have_text(state)


def test_filter_by_course(status_list, listed_statuses):
    """Status list: the course filter shows only that course's statuses."""
    status_list.filter_by_course(listed_statuses["course_name"])

    expect(status_list.course_filter.chips).to_have_text([listed_statuses["course_name"]])
    expect_shown(status_list, *listed_statuses["ids"].values())
    expect(status_list.page).to_have_url(re.compile(r"[?&]course=\d+"))


def test_combined_filters_and_reset(status_list, listed_statuses):
    """Status list: search, type and status filters combine; Reset clears them and shows everything."""
    total = status_list.result_count()

    status_list.search(listed_statuses["title"])
    status_list.filter_by_type("Edureel")
    status_list.filter_by_state("Disabled")

    expect_shown(status_list, listed_statuses["ids"]["off"])

    status_list.reset_filters()

    expect(status_list.search_input).to_have_value("")
    expect(status_list.type_filter).to_have_value("")
    expect(status_list.state_filter).to_have_value("")
    assert status_list.result_count() == total


def test_grid_and_list_view(status_list, listed_statuses):
    """Status list: the view buttons switch between cards (grid) and a table (list)."""
    status_list.search(listed_statuses["title"])
    expect(status_list.grid_view_button).to_have_class(re.compile(r"\bactive\b"))
    expect(status_list.results.locator(".st-card")).to_have_count(3)

    status_list.switch_to_list_view()

    expect(status_list.list_view_button).to_have_class(re.compile(r"\bactive\b"))
    expect(status_list.grid_view_button).not_to_have_class(re.compile(r"\bactive\b"))
    expect(status_list.list_headers).to_have_text(
        ["Preview", "Title", "Type", "Courses & links", "Status", "Expires", "Actions"]
    )
    expect_shown(status_list, *listed_statuses["ids"].values())
    expect(status_list.results.locator(".st-card")).to_have_count(0)
    expect(status_list.page).to_have_url(re.compile(r"[?&]view=list"))

    status_list.switch_to_grid_view()

    expect(status_list.list_table).to_have_count(0)
    expect(status_list.results.locator(".st-card")).to_have_count(3)


def test_view_and_filters_are_kept_after_reload(status_list, listed_statuses):
    """Status list: the search, filters and view mode are in the URL, so a reload keeps them."""
    status_list.search(listed_statuses["title"])
    status_list.filter_by_state("Live")
    status_list.switch_to_list_view()

    status_list.page.reload(wait_until="domcontentloaded")

    expect(status_list.search_input).to_have_value(listed_statuses["title"])
    expect(status_list.state_filter).to_have_value("live")
    expect(status_list.list_view_button).to_have_class(re.compile(r"\bactive\b"))
    expect_shown(status_list, listed_statuses["ids"]["reel"], listed_statuses["ids"]["snap"])


@pytest.mark.parametrize(
    "grouping, heading",
    [
        ("Group by month", r"^[A-Z][a-z]+ \d{4} \(3\)$"),  # e.g. "November 2026 (3)"
        ("Group by week", r"^Week of \d{2} [A-Z][a-z]{2} \d{4} \(3\)$"),  # e.g. "Week of 02 Nov 2026 (3)"
    ],
    ids=["month", "week"],
)
def test_group_by_month_and_week(status_list, listed_statuses, grouping, heading):
    """Status list: grouping adds a heading with the period and its count; "No grouping" removes it."""
    status_list.search(listed_statuses["title"])
    expect(status_list.group_titles).to_have_count(0)

    status_list.group_by(grouping)

    expect(status_list.group_titles).to_have_count(1)
    expect(status_list.group_titles).to_have_text(re.compile(heading))
    expect_shown(status_list, *listed_statuses["ids"].values())

    status_list.group_by("No grouping")

    expect(status_list.group_titles).to_have_count(0)


def test_pagination(status_list):
    """Status list: 12 statuses per page; the page links open the next page."""
    total = status_list.result_count()
    if total <= 12:
        pytest.skip(f"Paging needs more than 12 statuses on the channel (found {total})")
    expect(status_list.pager_summary).to_have_text(f"1–12 of {total}")
    first_page = status_list.shown_status_ids()

    status_list.open_page_number(2)

    expect(status_list.pager_summary).to_have_text(f"13–{min(24, total)} of {total}")
    assert not set(status_list.shown_status_ids()) & set(first_page)
