import base64
import os
from html import escape
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from config import BASE_URL
from pages.content_dashboard_page import ContentDashboardPage
from pages.login_page import LoginPage
from pages.staff_dashboard_page import StaffDashboardPage


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a local .env file. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(Path(__file__).parent / ".env")

# False = the browser window is shown while tests run; True = headless (no window).
HEADLESS = True

expect.set_options(timeout=10_000)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        print(f"\n[setup] Chromium {browser.version} launched with headless={HEADLESS}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def login_page(page):
    login_page = LoginPage(page)
    login_page.open()
    return login_page


@pytest.fixture
def staff_credentials():
    username = os.getenv("STAFF_USERNAME")
    password = os.getenv("STAFF_PASSWORD")
    if not username or not password:
        pytest.skip("STAFF_USERNAME / STAFF_PASSWORD environment variables are not set")
    return username, password


@pytest.fixture
def content_dashboard(login_page, staff_credentials):
    """Log in, open the Content Dashboard from the Staff Dashboard, and return its page object."""
    login_page.login(*staff_credentials)
    StaffDashboardPage(login_page.page).go_to_content_dashboard()
    content_dashboard = ContentDashboardPage(login_page.page)
    expect(content_dashboard.heading).to_be_visible()
    return content_dashboard


# ---------------------------------------------------------------------------
# HTML report (pytest-html): environment info, a "Reason" column, and a
# screenshot + page URL attached to every failed Playwright test.
# ---------------------------------------------------------------------------

# Playwright page fixtures used by the tests directly or through Page Objects.
PAGE_FIXTURES = ("page", "admin_page")
# Latest page created by each of those fixtures, so a failing fixture (setup error) can
# still be screenshotted: pytest does not expose earlier fixtures to the test in that case.
_pages = {}


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef):
    value = yield
    if fixturedef.argname in PAGE_FIXTURES:
        _pages[fixturedef.argname] = value
    return value


def pytest_configure(config):
    """Show the channel and browser mode in the report's Environment table."""
    if config.pluginmanager.hasplugin("metadata"):
        from pytest_metadata.plugin import metadata_key

        config.stash[metadata_key]["Base URL"] = BASE_URL
        config.stash[metadata_key]["Browser"] = f"Chromium (headless={HEADLESS})"


def _reason(report) -> str:
    """One-line failure message (or skip reason) for the report's Reason column."""
    if report.skipped and isinstance(report.longrepr, tuple):
        return report.longrepr[2].removeprefix("Skipped: ")
    if report.failed:
        crash = getattr(report.longrepr, "reprcrash", None)
        message = crash.message if crash else str(report.longrepr)
        lines = message.strip().splitlines()
        return lines[0] if lines else ""
    return ""


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_header(cells):
    cells.insert(3, '<th class="sortable" data-column-type="reason">Reason</th>')


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_row(report, cells):
    cells.insert(3, f'<td class="col-reason">{escape(_reason(report))}</td>')


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item):
    report = yield
    html_plugin = item.config.pluginmanager.getplugin("html")
    # One screenshot per failed test: a failing setup (fixture) or test body.
    if html_plugin is None or not report.failed or report.when == "teardown":
        return report

    used = getattr(item, "fixturenames", ())
    page = next((_pages[name] for name in PAGE_FIXTURES if name in used and name in _pages), None)
    if page is None or page.is_closed():
        return report

    extras = getattr(report, "extras", [])
    try:
        screenshot = page.screenshot(full_page=True, timeout=5_000)
        extras.append(html_plugin.extras.url(page.url, name="Page URL at failure"))
        extras.append(html_plugin.extras.png(base64.b64encode(screenshot).decode(), name="Failure screenshot"))
    except Exception as error:  # never let reporting hide the real test failure
        extras.append(html_plugin.extras.text(f"Screenshot not captured: {error}", name="Screenshot error"))
    report.extras = extras
    return report
