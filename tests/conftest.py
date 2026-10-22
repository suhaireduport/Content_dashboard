"""Fixtures shared by the Course and content hierarchy test files.

Hierarchy tests (Subject / Chapter / Topic / Subtopic) work only inside a test-only
"QA Auto Course <id>" created once per run and deleted, with its whole tree, at the end.
"""

import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from api.syllabus_api import SyllabusApi
from config import BASE_URL
from pages.course_page import CoursePage
from pages.login_page import LoginPage
from pages.staff_dashboard_page import StaffDashboardPage
from pages.subject_page import SubjectPage
from pages.video_mapping_page import MappedVideosPage, VideoListPage, VideoMapPage
from tests.data import COURSE_DATA
from tests.hierarchy_helpers import LEVEL_PAGES, PARENT_LEVEL, create_branch


@pytest.fixture
def course_page(content_dashboard):
    """Content Dashboard > Menu > Course."""
    content_dashboard.open_menu_item("Course")
    return CoursePage(content_dashboard.page)


@pytest.fixture(scope="session")
def admin_page(browser):
    """Logged-in page shared by the hierarchy tests (one login per run)."""
    username, password = os.getenv("STAFF_USERNAME"), os.getenv("STAFF_PASSWORD")
    if not username or not password:
        pytest.skip("STAFF_USERNAME / STAFF_PASSWORD environment variables are not set")
    context = browser.new_context()
    page = context.new_page()
    # The dev server occasionally takes >30s to reload a list after Save/Delete
    page.set_default_navigation_timeout(60_000)
    login_page = LoginPage(page)
    login_page.open()
    login_page.login(username, password)
    expect(page).to_have_url(StaffDashboardPage.URL_PATTERN)
    yield page
    context.close()


@pytest.fixture(scope="session")
def syllabus_api(admin_page):
    return SyllabusApi(admin_page.request)


@pytest.fixture(scope="session")
def qa_tree(admin_page):
    """Test-only course with one Subject > Chapter > Topic > Subtopic branch.

    {"course": id, "course_name": name, "subject"/"chapter"/"topic"/"subtopic": item}
    """
    tag = uuid4().hex[:8]
    course_name = f"QA Auto Course {tag}"
    courses = CoursePage(admin_page)
    courses.open()
    try:
        courses.create_course(course_name, **COURSE_DATA)
        tree = {"tag": tag, "course_name": course_name, "course": courses.course_id(course_name)}
        tree.update(create_branch(admin_page, tree["course"], tag))
        tree["subtopic"] = tree.pop("subtopic_1")
        yield tree
    finally:
        # Deleting the course deletes its whole Subject/Chapter/Topic/Subtopic tree. A delete
        # does not always stick on the first try, so check the course list and retry.
        for _ in range(3):
            courses.delete_courses_starting_with(course_name)
            remaining = admin_page.request.get(f"{BASE_URL}/core/get/course-list").json()["course_list"]
            if not any(course["title"] == course_name for course in remaining):
                break


@pytest.fixture
def level_page(request, admin_page, qa_tree):
    """Page Object for the test module's LEVEL, opened on the shared branch's parent."""
    level = request.module.LEVEL
    page_object = LEVEL_PAGES[level](admin_page)
    page_object.open(qa_tree[level]["parent"])
    return page_object


@pytest.fixture
def level_item_name(request, admin_page, qa_tree):
    """Unique test-only name for the module's LEVEL; leftovers are deleted after the test."""
    level = request.module.LEVEL
    name = f"QA Auto {LEVEL_PAGES[level].LEVEL} {uuid4().hex[:8]}"
    yield name
    LEVEL_PAGES[level](admin_page).delete_items_starting_with(qa_tree[level]["parent"], name)


@pytest.fixture
def empty_parent(request, admin_page, qa_tree):
    """Id of a new, empty parent for the module's LEVEL (a course for Subject, a subject for
    Chapter, ...). Deleted after the test."""
    parent_level = PARENT_LEVEL[request.module.LEVEL]
    tag = uuid4().hex[:8]
    if parent_level == "course":
        name = f"QA Auto Course {tag} empty"
        courses = CoursePage(admin_page)
        courses.open()
        courses.create_course(name, **COURSE_DATA)
        yield courses.course_id(name)
        courses.delete_courses_starting_with(name)
    else:
        parent_page = LEVEL_PAGES[parent_level](admin_page)
        name = f"QA Auto {parent_page.LEVEL} {tag} empty"
        grandparent_id = qa_tree[parent_level]["parent"]
        parent_page.open(grandparent_id)
        parent_page.create_item(name)
        yield parent_page.item_id(name)
        parent_page.delete_items_starting_with(grandparent_id, name)


@pytest.fixture(scope="session")
def video_id(admin_page):
    """An existing transcoded video, temporarily mapped to test subtopics only."""
    videos = VideoListPage(admin_page)
    videos.open()
    video = videos.first_mappable_video_id()
    yield video
    # Safety net: remove any mapping from this video to a test course that survived cleanup
    VideoMapPage(admin_page).unmap_rows_containing(video, "QA Auto Course")


@pytest.fixture
def branch(admin_page, qa_tree):
    """Fresh Subject > Chapter > Topic > 2 Subtopics under the QA course for one test.
    Video mappings are removed and the branch is deleted afterwards."""
    tag = uuid4().hex[:8]
    created = {}
    try:
        created.update(create_branch(admin_page, qa_tree["course"], tag, subtopics=2))
        yield created
    finally:
        mapped = MappedVideosPage(admin_page)
        for key in ("subtopic_1", "subtopic_2"):
            if key in created:
                mapped.unmap_all(created[key]["id"])
        if "subject" in created:
            SubjectPage(admin_page).delete_items_starting_with(qa_tree["course"], created["subject"]["name"])
