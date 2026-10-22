import re

from playwright.sync_api import expect

from pages.content_dashboard_page import ContentDashboardPage
from pages.login_page import LoginPage
from pages.staff_dashboard_page import StaffDashboardPage

LOGIN_URL_PATTERN = re.compile(r"/staff-dashboard/login/")


def test_login_page_opens_successfully(page):
    login_page = LoginPage(page)
    response = login_page.open()

    assert response is not None and response.ok, f"Unexpected status: {response and response.status}"
    expect(page).to_have_url(LoginPage.URL)


def test_login_page_heading_and_title_displayed(login_page):
    expect(login_page.page).to_have_title(LoginPage.PAGE_TITLE)
    expect(login_page.heading).to_be_visible()


def test_username_field_is_visible(login_page):
    expect(login_page.username_input).to_be_visible()
    expect(login_page.username_input).to_be_editable()


def test_password_field_is_visible(login_page):
    expect(login_page.password_input).to_be_visible()
    expect(login_page.password_input).to_be_editable()


def test_login_button_is_visible(login_page):
    expect(login_page.login_button).to_be_visible()
    expect(login_page.login_button).to_be_enabled()


def test_login_with_both_fields_empty(login_page):
    login_page.click_login()

    # Browser blocks submit: the first required field reports the error
    assert login_page.is_value_missing(login_page.username_input)
    assert login_page.validation_message(login_page.username_input) != ""
    expect(login_page.page).to_have_url(LoginPage.URL)


def test_login_with_username_empty(login_page):
    login_page.enter_password("SomePassword123")
    login_page.click_login()

    assert login_page.is_value_missing(login_page.username_input)
    assert login_page.validation_message(login_page.username_input) != ""
    expect(login_page.page).to_have_url(LoginPage.URL)


def test_login_with_password_empty(login_page):
    login_page.enter_username("someuser")
    login_page.click_login()

    assert login_page.is_value_missing(login_page.password_input)
    assert login_page.validation_message(login_page.password_input) != ""
    expect(login_page.page).to_have_url(LoginPage.URL)


def test_login_with_invalid_credentials(login_page):
    login_page.login("invalid_user_qa_automation", "WrongPassword123")

    expect(login_page.error_alert).to_be_visible()
    expect(login_page.error_alert).to_have_text(LoginPage.INVALID_CREDENTIALS_MESSAGE)
    expect(login_page.page).to_have_url(LOGIN_URL_PATTERN)


def test_login_with_valid_credentials(login_page, staff_credentials):
    username, password = staff_credentials
    login_page.login(username, password)

    # Login -> Staff Dashboard
    staff_dashboard = StaffDashboardPage(login_page.page)
    expect(staff_dashboard.page).to_have_url(StaffDashboardPage.URL_PATTERN)
    expect(staff_dashboard.page).to_have_title(StaffDashboardPage.PAGE_TITLE)
    expect(staff_dashboard.heading).to_be_visible()
    expect(login_page.error_alert).to_have_count(0)

    # Staff Dashboard -> Go To Content Dashboard
    expect(staff_dashboard.go_to_content_dashboard_link).to_be_visible()
    staff_dashboard.go_to_content_dashboard()

    # Content Dashboard
    content_dashboard = ContentDashboardPage(staff_dashboard.page)
    expect(content_dashboard.page).to_have_url(ContentDashboardPage.URL_PATTERN)
    expect(content_dashboard.page).to_have_title(ContentDashboardPage.PAGE_TITLE)
    expect(content_dashboard.heading).to_be_visible()


def test_password_field_masks_input(login_page):
    secret = "MaskedPass123"
    login_page.enter_password(secret)

    expect(login_page.password_input).to_have_attribute("type", "password")
    expect(login_page.password_input).to_have_value(secret)


def test_forgot_password_opens_modal(login_page):
    expect(login_page.forgot_password_button).to_be_visible()
    expect(login_page.forgot_password_dialog).to_be_hidden()

    login_page.open_forgot_password()
    expect(login_page.forgot_password_dialog).to_be_visible()
    expect(login_page.forgot_password_email_input).to_be_visible()
    expect(login_page.forgot_password_email_input).to_have_attribute("type", "email")
    expect(login_page.forgot_password_submit_button).to_be_visible()
