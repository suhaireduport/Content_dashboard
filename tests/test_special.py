"""Special Course page requirements and Grade course sorting.

Part 1: Course list (Dashboard > Courses) - tab loading/counts, archived course actions,
        mentor dropdown + mentor associations, active course edit/duplicate.
Part 2: Course sorting under a Grade (Dashboard > Grades > grade > Sort Courses).

All records are test-only ("QA Auto ..." courses and grades) and are deleted afterwards.
Course sorting only ever touches test grades, so real course orders are never changed.
"""

import re
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from api.course_api import CourseApi
from config import BASE_URL
from pages.course_page import CourseLabelsPage, CoursePage
from pages.grade_page import CourseSortPage, GradePage
from pages.staff_dashboard_page import MentorPoolPage
from pages.syllabus_level_page import ChangeLogPage
from tests.data import COURSE_DATA


# ---------- Helpers and fixtures ----------


def record_app_requests(page) -> list[str]:
    """Collect the app's own XHR/fetch requests (Cloudflare's /cdn-cgi/ beacons excluded)."""
    requests = []
    page.on(
        "request",
        lambda r: r.resource_type in ("xhr", "fetch")
        and r.url.startswith(BASE_URL)
        and "/cdn-cgi/" not in r.url
        and requests.append(r.url),
    )
    return requests


@pytest.fixture
def admin_course_api(admin_page):
    return CourseApi(admin_page.request)


@pytest.fixture
def qa_courses(admin_page):
    """Factory: create("suffix", is_active=..., mentors=..., grade=...) -> course name.
    Every course created through it is deleted after the test."""
    prefix = f"QA Auto Course {uuid4().hex[:8]}"
    courses = CoursePage(admin_page)

    def create(suffix: str, is_active: bool = True, mentors=(), grade: str | None = None) -> str:
        name = f"{prefix} {suffix}"
        data = {**COURSE_DATA, "grade": grade or COURSE_DATA["grade"]}
        courses.open()
        courses.create_course(name, **data, is_active=is_active, mentors=tuple(mentors))
        return name

    yield create
    delete_courses_and_verify(admin_page, prefix)


def delete_courses_and_verify(page, prefix: str) -> None:
    courses = CoursePage(page)
    for _ in range(3):  # a course delete does not always stick on the first try
        courses.delete_courses_starting_with(prefix)
        remaining = page.request.get(f"{BASE_URL}/core/get/course-list").json()["course_list"]
        if not any(course["title"].startswith(prefix) for course in remaining):
            return


@pytest.fixture(scope="module")
def sort_grades(admin_page):
    """Two test grades: "x" with 4 test courses, "y" with 2 test courses."""
    tag = uuid4().hex[:8]
    grades = GradePage(admin_page)
    courses = CoursePage(admin_page)
    course_prefix = f"QA Auto Course {tag}"
    data = {"tag": tag}
    try:
        for key, count in (("x", 4), ("y", 2)):
            grade_name = f"QA Auto Grade {tag} {key}"
            grades.open()
            grades.create_item(grade_name)
            data[key] = {"name": grade_name, "id": grades.grade_id(grade_name), "courses": {}}
            for letter in "ABCD"[:count]:
                title = f"{course_prefix} {key}{letter}"
                courses.open()
                courses.create_course(title, **{**COURSE_DATA, "grade": grade_name})
                data[key]["courses"][courses.course_id(title)] = title
        yield data
    finally:
        delete_courses_and_verify(admin_page, course_prefix)
        grades.delete_items_starting_with(f"QA Auto Grade {tag}")


# =====================================================================
# Part 1A: Page loading, counts and tabs
# (page load, Active-only, counts vs API and cards vs counts are covered in test_course.py)
# =====================================================================


def test_course_counts_correct_immediately_after_load(course_page):
    """Counts are shown right away, before the archived cards are loaded."""
    api = CourseApi(course_page.page.request)
    archived = api.list_archived_card_courses()
    active = course_page.tab_count(course_page.active_count)

    expect(course_page.visible_active_cards).to_have_count(active)
    assert course_page.tab_count(course_page.archived_count) == len(archived)
    assert course_page.tab_count(course_page.all_count) == active + len(archived)
    assert all(not course["active"] for course in archived)


def test_archived_courses_load_lazily_on_first_visit(course_page):
    page = course_page.page
    expect(page.locator('.course-card[data-active="false"]')).to_have_count(0)

    with page.expect_request(CourseApi.ARCHIVED_CARDS_URL):
        course_page.show_archived()

    archived_count = course_page.tab_count(course_page.archived_count)
    expect(course_page.visible_archived_cards).to_have_count(archived_count)
    expect(course_page.courses_loading).to_be_hidden()
    api_ids = {course["id"] for course in CourseApi(page.request).list_archived_card_courses()}
    ui_ids = set(course_page.visible_card_ids())
    assert ui_ids == api_ids


def test_all_tab_lists_active_courses_before_archived(course_page):
    course_page.load_all_courses()

    statuses = course_page.visible_card_statuses()

    first_archived = statuses.index(False) if False in statuses else len(statuses)
    misplaced = sum(statuses[first_archived:])
    assert misplaced == 0, f"{misplaced} active course(s) are listed after the first archived course in All"


def test_switching_tabs_shows_no_duplicates_or_repeat_loading(course_page):
    page = course_page.page
    tabs = {
        "active": (course_page.show_active, course_page.active_count),
        "archived": (course_page.show_archived, course_page.archived_count),
        "all": (course_page.show_all, course_page.all_count),
    }
    first_visit = {}
    for key, (show, count) in tabs.items():
        show()  # the first Archived visit may fetch the archived cards
        expect(course_page.visible_cards).to_have_count(course_page.tab_count(count))
        first_visit[key] = course_page.visible_card_ids()

    requests = record_app_requests(page)
    for key in ("active", "archived", "all", "archived", "active", "all"):
        show, count = tabs[key]
        show()
        ids = course_page.visible_card_ids()
        assert len(ids) == len(set(ids)), f"Duplicate courses in the {key} tab"
        assert len(ids) == course_page.tab_count(count)
        assert ids == first_visit[key], f"The {key} tab changed between visits"
        expect(course_page.courses_loading).to_be_hidden()
        expect(page.get_by_text(re.compile(r"Loading", re.I)).filter(visible=True)).to_have_count(0)

    assert requests == [], f"Already-loaded tabs were fetched again: {requests}"


# =====================================================================
# Part 1B: Archived course actions (compared with an active course)
# =====================================================================


@pytest.fixture
def archived_and_active(qa_courses):
    return {"archived": qa_courses("archived", is_active=False), "active": qa_courses("active", is_active=True)}


def test_archived_course_menu_matches_active_course(admin_page, archived_and_active):
    courses = CoursePage(admin_page)
    courses.open_with_all_courses()

    assert courses.card_menu_items(archived_and_active["archived"]) == list(CoursePage.MENU_ITEMS)
    assert courses.card_menu_items(archived_and_active["archived"]) == courses.card_menu_items(archived_and_active["active"])


@pytest.mark.parametrize("status", ["archived", "active"])
def test_course_labels_action(admin_page, archived_and_active, status):
    name = archived_and_active[status]
    courses = CoursePage(admin_page)
    courses.open_with_all_courses()
    course_id = courses.course_id(name)

    courses.open_labels(name)

    labels = CourseLabelsPage(admin_page)
    expect(admin_page).to_have_url(f"{BASE_URL}/core/syllabus-label/list/{course_id}")
    expect(labels.heading).to_be_visible()
    expect(labels.breadcrumb).to_contain_text(name)
    expect(labels.add_button).to_be_visible()


@pytest.mark.parametrize("status", ["archived", "active"])
def test_course_change_log_action(admin_page, archived_and_active, status):
    name = archived_and_active[status]
    courses = CoursePage(admin_page)
    courses.open_with_all_courses()

    courses.open_change_log(name)

    change_log = ChangeLogPage(admin_page, "Course")
    expect(change_log.heading).to_be_visible()
    assert change_log.event_names() == ["Created"]
    expect(change_log.event_data.first).to_contain_text(f"'is_active': {status == 'active'}")


@pytest.mark.parametrize("status", ["archived", "active"])
def test_duplicate_course_creates_matching_copy(admin_page, admin_course_api, archived_and_active, status):
    name = archived_and_active[status]
    copy_name = f"{name}{CoursePage.COPY_SUFFIX}"
    courses = CoursePage(admin_page)
    courses.open_with_all_courses()
    original_details = courses.card_details(name)

    courses.duplicate_course(name)

    expect(courses.success_alert.filter(has_text=CoursePage.DUPLICATE_MESSAGE)).to_be_visible()
    courses.open_with_all_courses()
    expect(courses.course_card(copy_name)).to_have_count(1)
    expected_status = CoursePage.ARCHIVED_STATUS if status == "archived" else CoursePage.ACTIVE_STATUS
    expect(courses.course_status_badge(copy_name)).to_have_text(expected_status)
    assert courses.card_details(copy_name) == original_details
    # The original is unchanged
    expect(courses.course_status_badge(name)).to_have_text(expected_status)
    assert courses.card_details(name) == original_details
    api = {course["title"]: course["active"] for course in admin_course_api.list_courses()}
    assert api.get(copy_name) is (status == "active") and api.get(name) is (status == "active")


@pytest.mark.parametrize("status", ["archived", "active"])
def test_course_edit_form_opens_with_saved_values(admin_page, archived_and_active, status):
    name = archived_and_active[status]
    courses = CoursePage(admin_page)
    courses.open_with_all_courses()

    courses.open_edit_popup(name)

    expect(courses.update_dialog).to_be_visible()
    expect(courses.update_title_input).to_have_value(name)
    for select, expected in (
        (courses.update_board, COURSE_DATA["board"]),
        (courses.update_grade, COURSE_DATA["grade"]),
        (courses.update_medium, COURSE_DATA["medium"]),
        (courses.update_stream, COURSE_DATA["stream"]),
    ):
        expect(select.locator("option:checked")).to_have_text(expected)
    if status == "active":
        expect(courses.update_is_active).to_be_checked()
    else:
        expect(courses.update_is_active).not_to_be_checked()


def test_delete_archived_course(admin_page, admin_course_api, archived_and_active):
    name = archived_and_active["archived"]
    courses = CoursePage(admin_page)
    courses.open_with_all_courses()

    courses.delete_course(name)

    expect(courses.success_alert.filter(has_text=CoursePage.DELETED_MESSAGE)).to_be_visible()
    courses.load_all_courses()
    expect(courses.course_card(name)).to_have_count(0)
    assert admin_course_api.find_courses(name) == []
    # The active test course is not affected
    expect(courses.course_card(archived_and_active["active"])).to_have_count(1)


# =====================================================================
# Part 1C: Mentor dropdown and course creation with mentors
# =====================================================================


def test_mentor_dropdown_loads_mentors_on_demand(admin_page):
    courses = CoursePage(admin_page)
    courses.open()
    expect(courses.create_mentor_options).to_have_count(0)  # not rendered with the page
    held = []
    # Hold the mentor request so the loading state can be checked before mentors arrive
    admin_page.route(CourseApi.MENTOR_LIST_URL, lambda route: held.append(route))
    try:
        with admin_page.expect_request(CourseApi.MENTOR_LIST_URL):
            courses.open_add_popup()

        expect(courses.create_mentor_loading_option).to_have_text(CoursePage.MENTORS_LOADING_TEXT)
        expect(courses.create_mentor_options).to_have_count(0)
        assert held, "Mentor request was not intercepted"
        held[0].continue_()
    finally:
        admin_page.unroute(CourseApi.MENTOR_LIST_URL)

    courses.wait_for_mentors()
    expect(courses.create_mentor_loading_option).to_have_count(0)
    assert courses.mentor_option_labels()


def test_mentor_options_match_api_name_and_active_student_count(admin_page, admin_course_api):
    courses = CoursePage(admin_page)
    courses.open()
    courses.open_add_popup()

    labels = courses.mentor_option_labels()
    ids = courses.mentor_option_ids()
    api_mentors = admin_course_api.mentor_list()

    assert labels, "No mentors in the dropdown"
    wrong_format = [label for label in labels if not CoursePage.MENTOR_OPTION_PATTERN.match(label)]
    assert wrong_format == [], f"Mentor options not in 'Name (count)' format: {wrong_format[:5]}"
    assert len(ids) == len(set(ids)), "Duplicate mentors in the dropdown"
    assert ids == [str(m["id"]) for m in api_mentors]
    assert labels == [f"{m['name']} ({m['active_students_count']})" for m in api_mentors]


def test_mentor_list_is_reused_when_form_reopened(admin_page):
    courses = CoursePage(admin_page)
    courses.open()
    courses.open_add_popup()
    first_open = courses.mentor_option_labels()
    first_ids = courses.mentor_option_ids()
    courses.close_add_popup()
    expect(courses.create_dialog).to_be_hidden()
    requests = record_app_requests(admin_page)

    courses.open_add_popup()

    second_open = courses.mentor_option_labels()
    second_ids = courses.mentor_option_ids()
    assert second_open == first_open
    # Uniqueness by mentor id: different mentors can share a display name
    assert second_ids == first_ids and len(second_ids) == len(set(second_ids)), "Mentors duplicated after reopening"
    expect(courses.create_mentor_loading_option).to_have_count(0)
    assert CourseApi.MENTOR_LIST_URL not in requests, f"Mentors were fetched again on reopen: {requests}"


def test_mentor_tag_can_be_removed_and_cancel_creates_nothing(admin_page, admin_course_api):
    courses = CoursePage(admin_page)
    courses.open()
    courses.open_add_popup()
    mentors = courses.mentor_option_labels()
    assert len(mentors) >= 2, "Need at least two mentors in the dropdown"
    first, second = mentors[:2]
    name = f"QA Auto Course {uuid4().hex[:8]} cancelled"
    courses.create_title_input.fill(name)

    courses.select_mentor(first)
    courses.select_mentor(second)
    expect(courses.create_mentor_tags).to_have_count(2)
    courses.remove_mentor_tag(first)

    expect(courses.create_mentor_tags).to_have_count(1)
    expect(courses.create_mentor_tags).to_contain_text(second)
    assert len(courses.create_mentors_input.input_value().split(",")) == 1
    courses.close_add_popup()
    expect(courses.create_dialog).to_be_hidden()
    assert admin_course_api.find_courses(name) == []


def test_create_course_with_mentors_saves_associations(admin_page, admin_course_api, qa_courses):
    courses = CoursePage(admin_page)
    courses.open()
    courses.open_add_popup()
    mentors = courses.mentor_option_labels()[:2]
    courses.close_add_popup()
    assert len(mentors) == 2, "Need at least two mentors in the dropdown"
    expected_names = sorted(re.sub(r"\s*\(\d+\)$", "", label) for label in mentors)

    name = qa_courses("mentors", mentors=mentors)

    expect(courses.success_alert.filter(has_text=CoursePage.CREATED_MESSAGE)).to_be_visible()
    course_id = courses.course_id(name)
    pool = MentorPoolPage(admin_page)
    pool.open()
    assert sorted(pool.mentor_names(course_id)) == expected_names
    assert sorted(admin_course_api.mentor_pool_names(course_id)) == expected_names


# =====================================================================
# Part 1D: Active course editing and duplication
# (duplicate of an active course: test_duplicate_course_creates_matching_copy[active])
# =====================================================================


@pytest.mark.skip(
    reason="Blocked: the Edit form requires 'Default Batch', and a test course has no batches. "
    "Creating a batch needs a course fee, expiry date and duration (a sellable record), so it is "
    "not created automatically. Enable once a test batch strategy is agreed."
)
def test_edit_active_course_persists(admin_page, admin_course_api, qa_courses):
    name = qa_courses("edit", is_active=True)
    courses = CoursePage(admin_page)
    courses.open()
    courses.open_edit_popup(name)
    courses.update_default_batch.select_option(index=1)
    courses.change_title_and_save(f"{name} Updated")
    courses.open()
    expect(courses.course_card(f"{name} Updated")).to_have_count(1)
    assert admin_course_api.find_courses(f"{name} Updated")


# =====================================================================
# Part 2: Course sorting under a Grade
# =====================================================================


def open_sort_page(page, grade: dict) -> CourseSortPage:
    """Dashboard > Grades > grade card > "Sort Courses"."""
    grades = GradePage(page)
    grades.open()
    grades.open_course_sort(grade["name"])
    sort_page = CourseSortPage(page)
    expect(page).to_have_url(f"{BASE_URL}/core/course/sort/{grade['id']}")
    return sort_page


def drag_into_order(sort_page: CourseSortPage, desired: list[str]) -> None:
    """Drag cards left to right until the page shows `desired` (titles)."""
    for index, title in enumerate(desired):
        current = sort_page.card_titles()
        if current[index] != title:
            sort_page.drag_onto(title, current[index])


def test_sort_four_courses_and_save(admin_page, admin_course_api, sort_grades):
    grade = sort_grades["x"]
    sort_page = open_sort_page(admin_page, grade)
    desired = list(reversed(sort_page.card_titles()))
    assert len(desired) >= 4

    drag_into_order(sort_page, desired)
    assert sort_page.card_titles() == desired
    title_to_id = {title: course_id for course_id, title in grade["courses"].items()}
    desired_ids = [title_to_id[title] for title in desired]
    assert sort_page.order_input.input_value().split(",") == desired_ids
    sort_page.save_changes()

    expect(sort_page.success_alert.filter(has_text=CourseSortPage.SORTED_MESSAGE)).to_be_visible()
    assert admin_course_api.course_sort_order(grade["id"]) == desired_ids, "Saved order differs from the submitted order"
    assert sort_page.card_titles() == desired


def test_saved_course_order_persists_after_refresh(admin_page, admin_course_api, sort_grades):
    grade = sort_grades["x"]
    sort_page = open_sort_page(admin_page, grade)
    sort_page.drag_onto(sort_page.card_titles()[-1], sort_page.card_titles()[0])
    sort_page.save_changes()
    saved_ids = admin_course_api.course_sort_order(grade["id"])

    for _ in range(2):
        admin_page.reload(wait_until="domcontentloaded")
        assert sort_page.card_ids() == saved_ids
        titles = sort_page.card_titles()
        assert [sort_page.prev_order(title) for title in titles] == [str(i) for i in range(1, len(titles) + 1)]


def test_drop_card_into_gap_between_cards(admin_page, sort_grades):
    grade = sort_grades["x"]
    sort_page = open_sort_page(admin_page, grade)
    errors = []
    admin_page.on("pageerror", lambda e: errors.append(str(e)))
    before = sort_page.card_titles()
    moving = before[-1]

    sort_page.drag_into_gap_after(moving, 0)

    after = sort_page.card_titles()
    assert errors == [], f"Page errors on drop: {errors}"
    assert after.index(moving) in (0, 1), f"Card dropped between positions 1 and 2 ended at {after.index(moving) + 1}"
    assert [t for t in after if t != moving] == [t for t in before if t != moving]
    assert sort_page.order_input.input_value().split(",") == sort_page.card_ids()


def test_drop_card_onto_itself_changes_nothing(admin_page, sort_grades):
    grade = sort_grades["x"]
    sort_page = open_sort_page(admin_page, grade)
    errors = []
    admin_page.on("pageerror", lambda e: errors.append(str(e)))
    before_titles, before_input = sort_page.card_titles(), sort_page.order_input.input_value()

    sort_page.drag_onto(before_titles[1], before_titles[1])

    assert errors == [], f"Page errors on drop: {errors}"
    assert sort_page.card_titles() == before_titles
    assert sort_page.order_input.input_value() == before_input


def test_save_without_changes_keeps_order(admin_page, admin_course_api, sort_grades):
    grade = sort_grades["x"]
    sort_page = open_sort_page(admin_page, grade)
    before = admin_course_api.course_sort_order(grade["id"])

    sort_page.save_changes()

    expect(sort_page.success_alert.filter(has_text=CourseSortPage.SORTED_MESSAGE)).to_be_visible()
    assert admin_course_api.course_sort_order(grade["id"]) == before
    assert sort_page.card_ids() == before


def test_sorting_one_grade_does_not_change_another(admin_page, admin_course_api, sort_grades):
    other_before = admin_course_api.course_sort_order(sort_grades["y"]["id"])
    sort_page = open_sort_page(admin_page, sort_grades["x"])
    drag_into_order(sort_page, list(reversed(sort_page.card_titles())))

    sort_page.save_changes()

    assert admin_course_api.course_sort_order(sort_grades["y"]["id"]) == other_before
    other = open_sort_page(admin_page, sort_grades["y"])
    assert other.card_ids() == other_before
