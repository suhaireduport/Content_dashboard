"""Content Dashboard > Status (/content/status/list): Edureels, Edusnaps and Edusnap sets.

Statuses are only posted to test-only "QA Auto Course <id>" courses, and every status
posted to them is deleted after each test. Status titles start with "atmn" (STATUS_PREFIX)
to tell them apart from manually added statuses. Videos and images are generated at run
time (see tests/status_media.py).

Observed behaviour (see report):
- Video length is not checked: a vertical 75s Edureel is saved like a 15s one (STATUS_003).
- Orientation is advisory: a non-9:16 video or image shows a warning but can still be saved.
- The image preview frame is 9:19.5 with object-fit: cover, so a 9:16 image is shown with
  its sides cut off (STATUS_005). The uploaded image itself is stored unchanged.
- When a course already has 3 live statuses, a 4th is refused unless "Replace oldest if
  course is full" is ticked; the oldest is then disabled, not deleted.
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from api.status_api import StatusApi
from pages.course_page import CoursePage
from pages.status_page import StatusPage
from tests.data import COURSE_DATA
from tests.status_media import png, png_size, serve_video

# Every status created by automation has a title (or caption) starting with this
STATUS_PREFIX = "atmn"

# Generated test media: (width, height, seconds)
VERTICAL_15S = (360, 640, 15)
VERTICAL_75S = (360, 640, 75)
LANDSCAPE_15S = (640, 360, 15)

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
        "Max 3 active per course · live for 24h after publishing / re-enabling"
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


def test_edusnap_preview_shows_whole_image(status_page):
    """STATUS_005: the preview shows the whole image, without cropping.

    Observed: fails. The preview frame is 9:19.5 with object-fit: cover, so the sides of a
    9:16 image are cut off."""
    status_page.open_add_popup()
    status_page.choose_type("Edusnap")

    status_page.add_images([png(1080, 1920)])

    expect(status_page.image_preview_meta(0)).to_have_text("1080×1920 · 9:16.0 ✓")
    assert status_page.image_preview_shows_whole_image(0)


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
        f'"{course_name}" already has 3 active status (limit 3).'
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
    [first_name], [(second_id, second_name)] = qa_course.values(), second_course.items()
    status_page.select_course(first_name)
    status_page.select_course(second_name)
    expect(status_page.course_picker.chips).to_have_text([second_name])

    status_page.enter_video_url(video(*VERTICAL_15S))
    status_page.choose_link(second_id, StatusPage.NO_LINK)
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
    option = next(option for option in status_api.link_options(course_id) if option["level"] == level)

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


def test_publish_requires_link_choice(status_page, qa_course, status_api, status_title, video):
    """STATUS_011: Save is refused until a link (or "No link") is chosen for the course."""
    [course_id] = qa_course
    status_page.fill_status("Edureel", qa_course, video_url=video(*VERTICAL_15S), links={}, title=status_title)
    expect(status_page.link_row(course_id)).to_be_visible()

    status_page.save()

    expect(status_page.field_error(f"link_{course_id}")).to_have_text('Choose a link, or "No link".')
    expect_rejected(status_page, status_api, status_title)

    status_page.choose_link(course_id, StatusPage.NO_LINK)
    expect(status_page.field_error(f"link_{course_id}")).to_be_empty()
    status_page.save()

    expect_saved(status_page)
    assert len(status_api.ids_matching(status_title)) == 1


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
