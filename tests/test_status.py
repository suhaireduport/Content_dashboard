"""Content Dashboard > Status (/content/status/list): Edureels, Edusnaps and Edusnap sets.

Statuses are only posted to test-only "QA Auto Course <id>" courses, and every status
posted to them is deleted after each test. Status titles start with "atmn" (STATUS_PREFIX)
to tell them apart from manually added statuses. Videos and images are generated at run
time (see tests/status_media.py).

Observed behaviour (see report):
- Video length is not checked: a vertical 75s Edureel is saved like a 15s one (STATUS_003).
- Orientation is advisory: a non-9:16 video or image shows a warning but can still be saved.
- The image preview is a phone mockup (9:19.5 screen, filled as in the app, shaded
  header/footer bands), so edges outside the phone screen are masked in the preview only.
  Images are cropped only through the crop editor; the uploaded image is stored unchanged.
- Crop editor: the 9:19.5 ratio produces a 1079×2340 image although the editor shows
  "Output 1080×2340" (other ratios match exactly).
- When a course already has 3 live statuses, a 4th is refused unless "Replace oldest if
  course is full" is ticked; the oldest is then disabled, not deleted.
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


def padded(image: dict, size: int) -> dict:
    """The same image file with trailing bytes added up to exactly `size` bytes (still decodable)."""
    return {**image, "buffer": image["buffer"] + bytes(size - len(image["buffer"]))}


def stored_image_sizes(status_page: StatusPage, status_api: StatusApi, status_id: str) -> list[tuple[int, int]]:
    """Sizes of a saved status's images, in the order they are shown in the app."""
    images = status_api.detail(status_id)["images"]
    return [image_size_at(status_page.page, image["url"]) for image in images]


def expect_saved(status_page: StatusPage) -> None:
    expect(status_page.toast(StatusPage.SAVED_MESSAGE)).to_be_visible()
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
        "Max 3 active per course · live for 24h from its publish date / re-enabling"
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
    """STATUS_003: a video longer than 60s cannot be published and a validation message is shown.

    Observed: fails. The preview reports 75s, but the status is saved and goes Live."""
    status_page.fill_status("Edureel", qa_course, video_url=video(*VERTICAL_75S), title=status_title)
    expect(status_page.video_preview_meta).to_have_text("360×640 · 9:16.0 · 75s ✓")

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

    Observed: [9x19.5] fails. The editor shows "Output 1080×2340", but the applied image is
    1079×2340 (the 9:19.5 ratio is stored rounded, 0.4615384615, so the width loses 1px)."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")
    status_page.add_images([png(1080, 1080)])
    status_page.open_image_editor(0)

    status_page.choose_crop_ratio(ratio)
    status_page.choose_output_width(width)

    expect(status_page.editor_output).to_have_text(output)

    status_page.apply_crop()

    expect(status_page.image_preview_meta(0)).to_have_text(output.removeprefix("Output "))


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


# ---------- STATUS_007: three live statuses per course ----------


def test_fourth_live_status_replaces_oldest(status_page, qa_course, status_api, status_title, video):
    """STATUS_007: with 3 live statuses in a course, a 4th is refused until "Replace oldest"
    is ticked; then the oldest is taken off (Disabled) and the course stays at 3 live."""
    [course_name] = qa_course.values()
    url = video(*VERTICAL_15S)
    for number in range(1, StatusPage.LIVE_LIMIT + 1):
        status_page.create_status("Edureel", qa_course, video_url=url, title=f"{status_title} {number}")
    assert status_api.course_hint(course_name) == "3/3 live"
    [oldest] = status_api.ids_matching(f"{status_title} 1")

    status_page.fill_status("Edureel", qa_course, video_url=url, title=f"{status_title} 4")
    status_page.save()

    expect(status_page.field_error("course")).to_contain_text(
        f'"{course_name}" already has 3 active status (limit 3) around that time. Oldest is #{oldest},'
    )
    expect(status_page.toast(StatusPage.COURSE_FULL_MESSAGE)).to_be_visible()
    expect_rejected(status_page, status_api, f"{status_title} 4")

    status_page.replace_oldest_checkbox.check()
    status_page.save()

    expect_saved(status_page)
    [newest] = status_api.ids_matching(f"{status_title} 4")
    assert status_api.course_hint(course_name) == "3/3 live"
    assert status_api.detail(oldest)["is_available"] is False
    status_page.open(status_title)
    expect(status_page.card_badges(oldest)).to_have_text(["Edureel", "Disabled"])
    expect(status_page.card_badges(newest)).to_have_text(["Edureel", "Live"])


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
    "post_type, expected", [("Edureel", ["reel", "off"]), ("Edusnap", ["snap"]), ("Edusnap set", [])],
    ids=["edureel", "edusnap", "edusnap-set"],
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
