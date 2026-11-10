"""Content Dashboard > Status > Analytics (/content/status/analytics).

The page is rendered on the server and has no JSON endpoint of its own, so what it shows is
checked against the Status API responses (api/status_api.py):
- counts: the total (data-count) of the Status list endpoint for the same filter;
- posts: /content/status/detail/<id> (title, type, state, publish date).
Views, "Watched fully" and Likes come from students using the app. No admin endpoint creates
or returns them, so they are checked as 0 for new posts and for consistency between tables.

Statuses are created only in a test-only "QA Auto Course <id> analytics" course, with titles
starting with "atmn" (STATUS_PREFIX), and are deleted with the course after the module.
The channel is shared: a status added or removed by someone else while this runs changes
the counts.

Observed behaviour (see report):
- The date under a post in "Latest 50 posts" is when it was created, not its publish date:
  a status scheduled 2 days ahead shows today's date (STATUS_ANALYTICS_006 [later]).
- The Views / Likes cards are higher than the sum of the posts' values (e.g. 45 views for
  2 posts with 3 + 2 views), as if deleted statuses still count (STATUS_ANALYTICS_008).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from api.status_api import StatusApi
from pages.course_page import CoursePage
from pages.status_analytics_page import StatusAnalyticsPage
from pages.status_page import StatusPage
from tests.data import COURSE_DATA, STATUS_PREFIX
from tests.status_media import png, serve_video

VERTICAL_15S = (360, 640, 15)

TYPE_NAMES = {int(value): name for name, value in StatusPage.TYPES.items()}  # post_type -> "Edureel" ...
STATE_NAMES = {"live": "Live", "scheduled": "Scheduled", "disabled": "Disabled", "expired": "Expired"}
ENGAGEMENT = {"Views": "views", "Watched fully": "watched_fully", "Likes": "likes"}

# Statuses created by analytics_statuses: name -> state it is left in
POSTS = {"reel": "live", "snap": "live", "off": "disabled", "later": "scheduled"}

# How the summary changes when analytics_statuses adds its 4 statuses
EXPECTED_CHANGE = {
    "All posts": 4, "Live now": 2, "Disabled": 1, "Expired": 0,
    "Views": 0, "Watched fully": 0, "Likes": 0,
    "Edureel": 2, "Edusnap": 1, "Edusnap set": 1,
}


@pytest.fixture(scope="module")
def status_api(admin_page):
    return StatusApi(admin_page.request)


@pytest.fixture
def analytics(admin_page):
    page_object = StatusAnalyticsPage(admin_page)
    page_object.open()
    return page_object


@pytest.fixture(scope="module")
def analytics_statuses(admin_page, status_api):
    """A test-only course with 4 statuses: a live Edureel, a live Edusnap, a disabled Edureel
    and an Edusnap set scheduled 2 days ahead (so its 24h never overlaps the others' and the
    course stays under 3 live). The analytics summary is read before and after adding them.
    Statuses and course are deleted after the module."""
    tag = uuid4().hex[:8]
    course_name = f"QA Auto Course {tag} analytics"
    title = f"{STATUS_PREFIX} QA Auto Status {tag}"
    titles = {name: f"{title} {name}" for name in POSTS}
    analytics = StatusAnalyticsPage(admin_page)
    courses = CoursePage(admin_page)
    status_page = StatusPage(admin_page)
    try:
        courses.open()
        courses.create_course(course_name, **COURSE_DATA)
        course_id = courses.course_id(course_name)
        course = {course_id: course_name}

        analytics.open()
        before = analytics.summary()

        status_page.open()
        url = serve_video(admin_page, *VERTICAL_15S)
        later = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        status_page.create_status("Edureel", course, video_url=url, title=titles["reel"])
        status_page.create_status("Edusnap", course, images=[png(1080, 1920)], title=titles["snap"])
        status_page.create_status("Edureel", course, video_url=url, title=titles["off"])
        status_page.create_status(
            "Edusnap set", course, images=[png(1080, 1920, "a.png"), png(720, 1280, "b.png")],
            title=titles["later"], publish_at=later,
        )
        admin_page.unroute(url)
        ids = {name: status_api.ids_matching(text)[0] for name, text in titles.items()}
        status_page.open(titles["off"])
        status_page.disable_status(ids["off"])

        analytics.open()
        after = analytics.summary()
        yield {
            "course_id": course_id, "course_name": course_name, "ids": ids, "titles": titles,
            "before": before, "after": after,
        }
    finally:
        status_api.delete_matching(course_name)
        courses.delete_courses_starting_with(course_name)


def api_counts(status_api: StatusApi) -> dict[str, int]:
    """The summary's count cards, as returned by the Status list endpoint."""
    return {
        "All posts": status_api.count(),
        "Live now": status_api.count(state="live"),
        "Disabled": status_api.count(state="disabled"),
        "Expired": status_api.count(state="expired"),
        **{name: status_api.count(type=value) for name, value in StatusPage.TYPES.items()},
    }


# ---------- Page ----------


def test_analytics_opens_from_status_list(admin_page):
    """STATUS_ANALYTICS_001: the Analytics button on the Status list opens the page with its
    summary cards and tables; "Back to Status" returns to the list."""
    status_page = StatusPage(admin_page)
    status_page.open()

    status_page.analytics_link.click()

    analytics = StatusAnalyticsPage(admin_page)
    expect(admin_page).to_have_url(StatusAnalyticsPage.URL_PATTERN)
    expect(analytics.heading).to_be_visible()
    expect(analytics.note).to_have_text("Counts only. Max 3 live per course.")
    expect(analytics.summary_labels).to_have_text(StatusAnalyticsPage.SUMMARY_LABELS)
    expect(analytics.course_headers).to_have_text(StatusAnalyticsPage.COURSE_HEADERS)
    expect(analytics.post_headers).to_have_text(StatusAnalyticsPage.POST_HEADERS)

    analytics.back_link.click()

    expect(admin_page).to_have_url(StatusPage.URL_PATTERN)
    expect(status_page.heading).to_be_visible()


# ---------- Summary cards ----------


def test_summary_counts_match_status_api(analytics, status_api):
    """STATUS_ANALYTICS_002: every count card equals the Status list API total for the same
    filter (All posts, Live, Disabled, Expired, and each type)."""
    shown = analytics.summary()
    expected = api_counts(status_api)

    assert {label: shown[label] for label in expected} == expected


def test_summary_counts_add_up(analytics, status_api):
    """STATUS_ANALYTICS_003: All posts = Edureel + Edusnap + Edusnap set, and = Live + Scheduled
    + Disabled + Expired (Scheduled has no card; it is taken from the API)."""
    shown = analytics.summary()

    assert shown["Edureel"] + shown["Edusnap"] + shown["Edusnap set"] == shown["All posts"]
    scheduled = status_api.count(state="scheduled")
    assert shown["Live now"] + scheduled + shown["Disabled"] + shown["Expired"] == shown["All posts"]


def test_new_statuses_are_counted(analytics_statuses):
    """STATUS_ANALYTICS_004: adding a live Edureel, a live Edusnap, a disabled Edureel and a
    scheduled Edusnap set changes each card by exactly that (a scheduled post is not Live)."""
    before, after = analytics_statuses["before"], analytics_statuses["after"]

    assert {label: after[label] - before[label] for label in after} == EXPECTED_CHANGE


# ---------- By course ----------


def test_course_row_matches_status_api(analytics, analytics_statuses, status_api):
    """STATUS_ANALYTICS_005: the By course row of the test course shows its live count out of 3
    (as in the Course picker's hint), its number of posts (as the API's course filter) and no
    engagement yet."""
    course_name = analytics_statuses["course_name"]

    row = analytics.course_row(course_name)

    assert row == {
        "course": course_name, "live": f"2/{StatusPage.LIVE_LIMIT}", "all_posts": len(POSTS),
        "views": 0, "watched_fully": 0, "likes": 0,
    }
    assert status_api.course_hint(course_name) == f"{row['live']} live"
    assert status_api.count(course=analytics_statuses["course_id"]) == row["all_posts"]


# ---------- Latest 50 posts ----------


@pytest.mark.parametrize("name", list(POSTS))
def test_post_row_matches_status_detail(analytics, analytics_statuses, status_api, name):
    """STATUS_ANALYTICS_006: a post's row shows the title, publish date, type and state returned
    by the status detail API, and no engagement yet.

    Observed: [later] fails. The row shows the date the scheduled post was created, not its
    publish date (e.g. "10 Nov 2026, 11:22" for a post publishing on 12 Nov 2026, 11:21)."""
    detail = status_api.detail(analytics_statuses["ids"][name])
    assert detail["state"] == POSTS[name]

    row = analytics.post_row(analytics_statuses["titles"][name])

    assert row == {
        "title": detail["title"],
        "published": datetime.fromisoformat(detail["publish_at"]).strftime(StatusAnalyticsPage.DATE_FORMAT),
        "type": TYPE_NAMES[detail["post_type"]],
        "state": STATE_NAMES[detail["state"]],
        "views": 0, "watched_fully": 0, "likes": 0,
    }


def test_latest_posts_are_newest_first_and_at_most_50(analytics):
    """STATUS_ANALYTICS_007: the table lists min(50, All posts) posts, newest publish date first."""
    total = analytics.summary()["All posts"]

    rows = analytics.post_table_rows()

    assert len(rows) == min(StatusAnalyticsPage.LATEST_LIMIT, total)
    dates = [datetime.strptime(row["published"], StatusAnalyticsPage.DATE_FORMAT) for row in rows]
    assert dates == sorted(dates, reverse=True)


# ---------- Engagement ----------


def test_engagement_totals_match_posts(analytics):
    """STATUS_ANALYTICS_008: Views, Watched fully and Likes in the summary are the sums of the
    posts' values (checked when all posts fit in the Latest 50 table).

    Observed: fails. With 2 posts showing 3 + 2 views and 3 + 2 likes, the cards show 45 views
    and 18 likes (the By course row shows 17 and 9), as if deleted statuses still count."""
    total = analytics.summary()["All posts"]
    if total > StatusAnalyticsPage.LATEST_LIMIT:
        pytest.skip(f"Needs at most {StatusAnalyticsPage.LATEST_LIMIT} posts on the channel (found {total})")
    shown = analytics.summary()
    rows = analytics.post_table_rows()

    sums = {label: sum(row[key] for row in rows) for label, key in ENGAGEMENT.items()}

    assert {label: shown[label] for label in ENGAGEMENT} == sums
