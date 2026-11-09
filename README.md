# Staff Dashboard – Login Automation

Python + Playwright + Pytest (Page Object Model). Headless or headed is set by `HEADLESS`
in [conftest.py](conftest.py) (`False` = browser window shown, `True` = headless).

## Channel (base URL)

All pages, logins and API calls use `BASE_URL` from [config.py](config.py):

```python
BASE_URL = "https://dev.eduport.co.in"
```

To test another Eduport channel, change only that line. Nothing else needs editing.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Credentials (for the valid-login test)

Valid credentials are read from environment variables and are never stored in code.
If they are not set, `test_login_with_valid_credentials` is skipped.

macOS / Linux:

```bash
export STAFF_USERNAME="your_username"
export STAFF_PASSWORD="your_password"
```

Windows (PowerShell):

```powershell
$env:STAFF_USERNAME="your_username"
$env:STAFF_PASSWORD="your_password"
```

## Run

```bash
pytest -s tests/test_login.py
```

## HTML report

Every run writes a single, self-contained HTML report (pytest-html, configured in
[pytest.ini](pytest.ini)) to `reports/report.html`. It is overwritten on each run.

```bash
open reports/report.html          # macOS
start reports\report.html         # Windows
```

Allure still works alongside it: `pytest --alluredir=allure-results`.
# Content_dashboard
