"""Page Object for the Staff Dashboard Login page."""

from playwright.sync_api import Page, Response

from config import BASE_URL


class LoginPage:
    URL = f"{BASE_URL}/staff-dashboard/login/"
    PAGE_TITLE = "Login - Eduport Dashboard"
    INVALID_CREDENTIALS_MESSAGE = (
        "Please enter a correct username and password. "
        "Note that both fields may be case-sensitive."
    )

    def __init__(self, page: Page):
        self.page = page

        # Login form
        self.heading = page.get_by_role("heading", name="Login", exact=True)
        # Role-based locators are used because get_by_label("Password") also
        # matches the "Forgot Password?" modal (aria-labelledby).
        self.username_input = page.get_by_role("textbox", name="Username")
        self.password_input = page.get_by_role("textbox", name="Password")
        self.login_button = page.get_by_role("button", name="Login", exact=True)

        # Server-side error shown after a failed login (no role/test-id available)
        self.error_alert = page.locator(".alert-danger")

        # Forgot Password modal
        self.forgot_password_button = page.get_by_role("button", name="Forgot Password?")
        self.forgot_password_dialog = page.get_by_role("dialog", name="Forgot Password?")
        self.forgot_password_email_input = self.forgot_password_dialog.get_by_role(
            "textbox", name="Your email address"
        )
        self.forgot_password_submit_button = self.forgot_password_dialog.get_by_role(
            "button", name="Submit"
        )

    # ---------- Actions ----------

    def open(self) -> Response | None:
        return self.page.goto(self.URL)

    def enter_username(self, username: str) -> None:
        self.username_input.fill(username)

    def enter_password(self, password: str) -> None:
        self.password_input.fill(password)

    def click_login(self) -> None:
        self.login_button.click()

    def login(self, username: str, password: str) -> None:
        self.enter_username(username)
        self.enter_password(password)
        self.click_login()

    def open_forgot_password(self) -> None:
        self.forgot_password_button.click()

    # ---------- Read helpers (used by assertions in tests) ----------

    def is_value_missing(self, field) -> bool:
        """True when the browser's HTML5 'required' validation fails for the field."""
        return field.evaluate("el => el.validity.valueMissing")

    def validation_message(self, field) -> str:
        """Native browser validation message, e.g. 'Please fill out this field.'"""
        return field.evaluate("el => el.validationMessage")
