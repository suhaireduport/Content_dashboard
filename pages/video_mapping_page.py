"""Page Objects for mapping video content to a subtopic.

Content cannot be uploaded from tests (videos are uploaded to cloud storage), so an
existing video is temporarily mapped to a test subtopic and the mapping is removed
afterwards. Mapping only adds/removes a mapping row; the video itself is not edited.

  VideoListPage     /content/video/list/                     find a video that can be mapped
  VideoMapPage      /content/video/map/list/<video id>        "Map Video Content" popup
  MappedVideosPage  /content/reverse/video/map/list/<subtopic id>  a subtopic's mapped videos
"""

import re

from playwright.sync_api import Page

from config import BASE_URL


class VideoListPage:
    URL = f"{BASE_URL}/content/video/list/"

    def __init__(self, page: Page):
        self.page = page
        # Only transcoded videos have a "Map TO" link
        self.map_links = page.get_by_role("link", name="Map TO")

    def open(self) -> None:
        self.page.goto(self.URL, wait_until="domcontentloaded")

    def first_mappable_video_id(self) -> str:
        href = self.map_links.first.get_attribute("href")  # /content/video/map/list/<id>
        return href.rstrip("/").rsplit("/", 1)[-1]


class VideoMapPage:
    MAPPED_MESSAGE = "Syllabus mapped with Video successfully!"

    def __init__(self, page: Page):
        self.page = page
        self.add_button = page.get_by_role("button", name=re.compile(r"^\W*Add$"))
        self.map_dialog = page.get_by_role("dialog", name="Map Video Content")
        self.map_to_select = self.map_dialog.locator("#map-to-choices")
        self.course_select = self.map_dialog.locator("#course-choices")
        self.subject_select = self.map_dialog.locator("#subject-choices")
        self.chapter_select = self.map_dialog.locator("#chapter-choices")
        self.topic_select = self.map_dialog.locator("#topic-choices")
        self.subtopic_select = self.map_dialog.locator("#subtopic-choices")
        self.save_button = self.map_dialog.get_by_role("button", name="Save")

        self.mapping_rows = page.locator("table tbody tr")
        self.delete_page_delete_button = page.locator(".card-footer").get_by_role(
            "button", name="Delete All"
        )
        self.delete_confirm_button = page.get_by_role(
            "dialog", name=re.compile(r"^Are you sure you want to delete")
        ).get_by_role("button", name="Delete")

    def open(self, video_id: str) -> None:
        self.page.goto(f"{BASE_URL}/content/video/map/list/{video_id}", wait_until="domcontentloaded")

    def rows_containing(self, text: str):
        return self.mapping_rows.filter(has_text=text)

    def unmap_rows_containing(self, video_id: str, text: str, attempts: int = 3) -> None:
        """Clean-up helper: delete this video's mapping rows that mention `text`
        (e.g. "QA Auto Course"). A fresh page is re-checked because a delete does not
        always stick on the first try."""
        for _ in range(attempts):
            self.open(video_id)
            rows = self.rows_containing(text)
            if rows.count() == 0:
                return
            while rows.count() > 0:
                rows.first.get_by_role("link", name=re.compile(r"^Delete")).click()
                self.page.wait_for_url(re.compile(r"/content/video/map/delete\?"), wait_until="domcontentloaded")
                self.delete_page_delete_button.click()
                with self.page.expect_navigation(wait_until="domcontentloaded"):
                    self.delete_confirm_button.click()
                self.open(video_id)

    def _select_when_loaded(self, select, value: str) -> None:
        # Each select's options are fetched after the previous one changes
        select.locator(f"option[value='{value}']").wait_for(state="attached")
        select.select_option(value)

    def map_to_subtopic(self, course_id, subject_id, chapter_id, topic_id, subtopic_id) -> None:
        self.add_button.click()
        self.map_to_select.select_option(label="Subtopic")
        self._select_when_loaded(self.course_select, str(course_id))
        self._select_when_loaded(self.subject_select, str(subject_id))
        self._select_when_loaded(self.chapter_select, str(chapter_id))
        self._select_when_loaded(self.topic_select, str(topic_id))
        self._select_when_loaded(self.subtopic_select, str(subtopic_id))
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.save_button.click()


class MappedVideosPage:
    UNMAPPED_MESSAGE = "Syllabus Content Mapping Deleted successfully!"

    def __init__(self, page: Page):
        self.page = page
        self.video_titles = page.locator(".page-content h3")
        self.unmap_links = page.locator(".page-content").get_by_role("link", name=re.compile(r"^Delete"))
        self.delete_page_delete_button = page.locator(".card-footer").get_by_role(
            "button", name="Delete All"
        )
        self.delete_confirm_button = page.get_by_role(
            "dialog", name=re.compile(r"^Are you sure you want to delete")
        ).get_by_role("button", name="Delete")

    def open(self, subtopic_id: str) -> None:
        self.page.goto(
            f"{BASE_URL}/content/reverse/video/map/list/{subtopic_id}", wait_until="domcontentloaded"
        )

    def unmap_first(self) -> None:
        self.unmap_links.first.click()
        self.page.wait_for_url(re.compile(r"/content/video/map/delete\?"), wait_until="domcontentloaded")
        self.delete_page_delete_button.click()
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.delete_confirm_button.click()

    def unmap_all(self, subtopic_id: str) -> None:
        """Remove every video mapped to the subtopic (only used on test subtopics)."""
        self.open(subtopic_id)
        while self.unmap_links.count() > 0:
            self.unmap_first()
            self.open(subtopic_id)
