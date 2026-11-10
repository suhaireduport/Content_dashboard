import base64
import inspect
import os
import re
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


# ---------- "Failure Explanation" column ----------
# Built from the failure message, the test's docstring (its goal, and any "Observed: ...
# fails" note documenting a known application issue) and the phase that failed.

ROOT_CAUSE_UNKNOWN = "Root cause requires further investigation."


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _docstring(item) -> str:
    return inspect.getdoc(getattr(item, "obj", None)) or ""


def _test_goal(item) -> str:
    """What the test checks: the first paragraph of its docstring or, without one, its name
    (e.g. test_chapter_unknown_id_has_no_server_error -> "Chapter unknown id has no server error.")."""
    summary = _docstring(item).split("\n\n")[0]
    if summary:
        return _short(summary)
    name = getattr(item, "originalname", None) or item.name.split("[")[0]
    words = name.removeprefix("test_").replace("_", " ").strip()
    return f"{words[:1].upper()}{words[1:]}." if words else ""


def _known_issue(item) -> str:
    """The test's "Observed: [ids] fails. <note>" docstring note, if it applies to this run."""
    match = re.search(r"Observed:\s*(?:\[([^\]]+)\]\s*)?fails\.?\s*(.*?)(?:\n\s*\n|\Z)", _docstring(item), re.S)
    if not match:
        return ""
    ids, note = match.groups()
    callspec = getattr(item, "callspec", None)
    if ids and (callspec is None or callspec.id not in [i.strip() for i in ids.split(",")]):
        return ""
    return _short(note) or "The test documents this failure as a known application issue."


def _analyse(message: str) -> tuple[str, str, str]:
    """(expected check, actual result, why) read from a failure message; "" when unknown."""
    lines = [line.strip() for line in message.strip().splitlines()]
    first = lines[0] if lines else ""
    error_type, _, text = first.partition(": ") if re.match(r"^[\w.]+: ", first) else ("", "", first)
    error_type = error_type.rsplit(".", 1)[-1]
    actual_value = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("Actual value:")), None)
    error_line = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("Error:")), "")
    waiting_for = re.search(r"waiting for (.+)", message)
    element = _short(waiting_for.group(1), 150) if waiting_for else ""

    # Playwright assertion, e.g. "Locator expected to have text 'X'" + "Actual value: Y"
    playwright = re.match(r"^(Locator|Page) expected (.+)$", text)
    if playwright:
        subject = "element" if playwright.group(1) == "Locator" else "page"
        check = playwright.group(2)
        expected = f"The {subject} was expected {_short(check)}" + (f" ({element})" if element else "")
        if "not found" in error_line:
            return expected, "The element was not found on the page.", (
                "The expected element never appeared: the step before it may not have worked, "
                "or the page layout or text has changed."
            )
        if "strict mode violation" in error_line:
            count = re.search(r"resolved to (\d+) elements", error_line)
            found = f"{count.group(1)} matching elements were" if count else "Several matching elements were"
            return expected, f"{found} found instead of one.", (
                "The locator is ambiguous: more than one element on the page matches it "
                "(for example an older message still on screen)."
            )
        actual = "The element was empty." if actual_value == "empty" else f"The {subject} showed: {_short(actual_value or 'nothing')}"
        if "count" in check:
            why = "The number of matching elements on the page is different from what the test expects."
        elif re.search(r"text|value|attribute|class|css|url|title", check):
            why = "The value shown on the page is different from the expected value."
        elif re.search(r"visible|hidden|empty|enabled|disabled|checked", check):
            why = "The element is not in the state the test expects."
        else:
            why = "The page did not reach the expected state within the time limit."
        return expected, actual, why

    if "Timeout" in text and "exceeded" in text:
        return (
            "The page action to finish within the time limit" + (f" ({element})" if element else ""),
            _short(text),
            "The page did not respond in time: the element never became available "
            "(slow server, or the page has changed).",
        )

    # Plain "assert" comparison; pytest shows the values (left = value from the app)
    if text.startswith("assert "):
        differing = []
        if "Differing items:" in lines:
            for line in lines[lines.index("Differing items:") + 1:]:
                if not line or line.startswith(("Full diff", "Use -v", "...")):
                    break
                differing.append(line)
        extra = [line for line in lines if re.match(r"(Left|Right) contains \d+ more item", line)]
        if differing:
            pairs = [line.split(" != ", 1) for line in differing if " != " in line]
            return (
                f"expected {'; '.join(right for _, right in pairs)}" if pairs else _short(text),
                f"Got {'; '.join(left for left, _ in pairs)}" if pairs else _short(text),
                "The values returned by the application are different from the expected values.",
            )
        compare = re.match(r"^assert (.+?) (==|!=|<=|>=|<|>|not in|in|is not|is) (.+)$", text)
        if compare:
            left, operator, right = compare.groups()
            detail = f" ({'; '.join(extra)})" if extra else ""
            words = {
                "==": "equal to", "!=": "different from", "<": "less than", ">": "greater than",
                "<=": "at most", ">=": "at least", "in": "contained in", "not in": "not contained in",
                "is": "", "is not": "not",
            }[operator]
            return (
                f"A value {words} {_short(right, 200)}".replace("  ", " "),
                f"{_short(left, 200)}{detail}",
                "The value returned by the application is different from the expected value.",
            )
        return "", _short(text), ROOT_CAUSE_UNKNOWN

    if error_type == "AssertionError":
        why = (
            "The server failed with an internal error (HTTP 5xx) instead of handling the request; "
            "this is a server-side bug."
            if re.search(r"HTTP 5\d\d|server error", text, re.I)
            else "The application did not behave as the test requires (see Actual)."
        )
        return "", _short(text), why

    unpack = re.match(r"not enough values to unpack \(expected (\d+), got (\d+)\)", text)
    if unpack:
        return (
            f"Exactly {unpack.group(1)} matching item(s)",
            f"{unpack.group(2)} matching item(s) were found.",
            "A lookup (for example a search through the API) returned fewer results than expected, "
            "so the item was probably not created or not found.",
        )
    if text.startswith("too many values to unpack"):
        return (
            "Exactly one matching item",
            "More matching items were found than expected.",
            "Duplicate or leftover data matches the same search.",
        )
    if error_type == "StopIteration":
        return "A matching item", "No matching item was found.", "A search for an item returned nothing."

    return "", _short(f"{error_type}: {text}" if error_type else text), ROOT_CAUSE_UNKNOWN


def _failure_explanation(item, report) -> str:
    """HTML for the Failure Explanation cell of a failed setup, test or teardown."""
    crash = getattr(report.longrepr, "reprcrash", None)
    message = crash.message if crash else str(report.longrepr)
    check, actual, why = _analyse(message)
    goal = _test_goal(item)

    if report.when == "call":
        expected = " ".join(part for part in (goal, f"Failed check: {check}." if check else "") if part)
        known = _known_issue(item)
        if known:
            why = f"Known application issue, documented in the test: {known}"
    else:
        expected = f"The test {report.when} (fixtures) to complete" + (f" for: {goal}" if goal else ".")
        stage = "before the test ran, so the test itself was not executed" if report.when == "setup" else "after the test ran"
        why = f"A {report.when} step failed {stage}. {why or ROOT_CAUSE_UNKNOWN}"

    parts = {"Expected": expected or ROOT_CAUSE_UNKNOWN, "Actual": actual or ROOT_CAUSE_UNKNOWN, "Why": why or ROOT_CAUSE_UNKNOWN}
    return "<br>".join(f"<b>{label}:</b> {escape(value)}" for label, value in parts.items())


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_header(cells):
    cells.insert(3, '<th class="sortable" data-column-type="reason">Reason</th>')
    cells.insert(4, '<th class="col-explanation">Failure Explanation</th>')


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_row(report, cells):
    cells.insert(3, f'<td class="col-reason">{escape(_reason(report))}</td>')
    explanation = getattr(report, "failure_explanation", "") if report.failed else ""
    cells.insert(4, f'<td class="col-explanation" style="min-width: 320px">{explanation or "N/A"}</td>')


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item):
    report = yield
    if report.failed:
        try:
            report.failure_explanation = _failure_explanation(item, report)
        except Exception:  # never let reporting hide the real test failure
            report.failure_explanation = escape(ROOT_CAUSE_UNKNOWN)
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
