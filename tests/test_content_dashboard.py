from playwright.sync_api import expect

from pages.content_dashboard_page import ContentDashboardPage


def test_content_dashboard_menu_items_are_visible(content_dashboard):
    expect(content_dashboard.page).to_have_url(ContentDashboardPage.URL_PATTERN)

    for name in ContentDashboardPage.TOP_MENU_ITEMS:
        expect(content_dashboard.menu_link(name)).to_be_visible()

    for section, items in ContentDashboardPage.MENU_SECTIONS.items():
        expect(content_dashboard.menu_section_title(section)).to_be_visible()
        for name in items:
            expect(content_dashboard.menu_link(name)).to_be_visible()
