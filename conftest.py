import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

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

# This project runs HEADLESS ONLY. There is intentionally no option to run headed.
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
