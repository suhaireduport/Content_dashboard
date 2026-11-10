"""Page Object for Content Dashboard > Status > Analytics (/content/status/analytics).

A server-rendered page (no AJAX): summary cards with counts, a "By course" table and a
"Latest 50 posts" table. Opened from the "Analytics" button on the Status list.
"""

import re

from playwright.sync_api import Locator, Page

from config import BASE_URL

# Reads a table body into one list of cell texts per row
_ROWS_JS = "rows => rows.map(row => [...row.cells].map(cell => cell.innerText.trim()))"


class StatusAnalyticsPage:
    URL = f"{BASE_URL}/content/status/analytics"
    URL_PATTERN = re.compile(r"/content/status/analytics")

    SUMMARY_LABELS = [
        "All posts", "Live now", "Disabled", "Expired", "Views", "Watched fully", "Likes",
        "Edureel", "Edusnap", "Edusnap set",
    ]
    COURSE_HEADERS = ["Course", "Live", "All posts", "Views", "Watched fully", "Likes"]
    POST_HEADERS = ["Post", "Type", "State", "Views", "Watched fully", "Likes"]
    LATEST_LIMIT = 50
    NO_TITLE = "(no title)"
    DATE_FORMAT = "%d %b %Y, %H:%M"  # date under a post's title, e.g. "09 Nov 2026, 17:28"

    def __init__(self, page: Page):
        self.page = page
        self.heading = page.get_by_role("heading", name="STATUS ANALYTICS", level=1)
        self.note = self.heading.locator("xpath=following-sibling::div")
        self.back_link = page.get_by_role("link", name=re.compile(r"Back to Status$"))

        # Summary cards: a label (.st-muted) and a number (.st-num)
        self.summary_cards = page.locator(".page-content .card-body").filter(has=page.locator(".st-num"))
        self.summary_labels = self.summary_cards.locator(".st-muted")

        self.course_table = self._table("By course")
        self.course_headers = self.course_table.locator("thead th")
        self.course_rows = self.course_table.locator("tbody tr")

        self.post_table = self._table("Latest 50 posts")
        self.post_headers = self.post_table.locator("thead th")
        self.post_rows = self.post_table.locator("tbody tr")

    def _table(self, title: str) -> Locator:
        card = self.page.locator(".card").filter(has=self.page.get_by_role("heading", name=title, exact=True))
        return card.locator("table")

    def open(self) -> None:
        self.page.goto(self.URL, wait_until="domcontentloaded")

    # ---------- Reading the page ----------

    def summary_value(self, label: str) -> Locator:
        card = self.summary_cards.filter(has=self.page.locator(".st-muted").get_by_text(label, exact=True))
        return card.locator(".st-num")

    def summary(self) -> dict[str, int]:
        """{card label: number} for every summary card."""
        pairs = self.summary_cards.evaluate_all(
            """cards => cards.map(card => [card.querySelector('.st-muted').innerText.trim(),
                                           card.querySelector('.st-num').innerText.trim()])"""
        )
        return {label: int(number) for label, number in pairs}

    def course_table_rows(self) -> list[dict]:
        """By course: [{"course", "live" (e.g. "2/3"), "all_posts", "views", "watched_fully", "likes"}]."""
        return [
            {"course": course, "live": live, "all_posts": int(posts), "views": int(views),
             "watched_fully": int(watched), "likes": int(likes)}
            for course, live, posts, views, watched, likes in self.course_rows.evaluate_all(_ROWS_JS)
        ]

    def course_row(self, course_name: str) -> dict:
        [row] = [row for row in self.course_table_rows() if row["course"] == course_name]
        return row

    def post_table_rows(self) -> list[dict]:
        """Latest 50 posts: [{"title", "published", "type", "state", "views", "watched_fully", "likes"}].
        The Post cell holds the title with the publish date under it."""
        rows = self.post_rows.evaluate_all(
            """rows => rows.map(row => {
                const [post, ...cells] = [...row.cells];
                const date = post.querySelector('.st-muted');
                const title = [...post.childNodes].filter(n => n !== date).map(n => n.textContent).join('');
                return [title.trim(), date ? date.innerText.trim() : '', ...cells.map(c => c.innerText.trim())];
            })"""
        )
        return [
            {"title": title, "published": published, "type": post_type, "state": state,
             "views": int(views), "watched_fully": int(watched), "likes": int(likes)}
            for title, published, post_type, state, views, watched, likes in rows
        ]

    def post_row(self, title: str) -> dict:
        [row] = [row for row in self.post_table_rows() if row["title"] == title]
        return row
