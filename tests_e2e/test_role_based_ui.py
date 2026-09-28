import re

from playwright.sync_api import expect


def test_management_menu_disabled_for_non_admin(logged_in_page, base_url):
    page = logged_in_page
    page.goto("/manage")
    users_link = page.locator(".management-menu-item", has_text="User Management")
    quotes_link = page.locator(".management-menu-item", has_text="Manage Quotes")

    expect(users_link).to_have_class("management-menu-item disabled")
    expect(users_link).to_have_attribute("href", "#")
    expect(quotes_link).to_have_class("management-menu-item disabled")
    expect(quotes_link).to_have_attribute("href", "#")
    expect(page.locator(".role-warning")).to_be_visible()


def test_management_menu_enabled_and_working_for_admin(admin_page, base_url):
    page = admin_page
    page.goto("/manage")
    users_link = page.locator(".management-menu-item", has_text="User Management")
    quotes_link = page.locator(".management-menu-item", has_text="Manage Quotes")

    expect(users_link).not_to_have_class(re.compile("disabled"))
    expect(users_link).to_have_attribute("href", "/manage/users")
    expect(quotes_link).not_to_have_class(re.compile("disabled"))
    expect(quotes_link).to_have_attribute("href", "/manage/quotes")
    expect(page.locator(".role-warning")).to_have_count(0)

    users_link.click()
    expect(page).to_have_url(base_url + "/manage/users")
    expect(page.locator(".users-table")).to_be_visible()


def test_direct_navigation_to_manage_users_as_non_admin_returns_403(logged_in_page, base_url):
    page = logged_in_page
    response = page.goto("/manage/users")
    assert response.status == 403
    expect(page.locator(".users-table")).to_have_count(0)


def test_direct_navigation_to_manage_quotes_as_non_admin_returns_403(logged_in_page, base_url):
    page = logged_in_page
    response = page.goto("/manage/quotes")
    assert response.status == 403
    expect(page.locator(".quotes-table")).to_have_count(0)


def test_direct_navigation_to_manage_users_as_anonymous_redirects_to_login(page, base_url):
    page.goto("/manage/users")
    expect(page).to_have_url(base_url + "/login")


def test_direct_navigation_to_manage_as_anonymous_redirects_to_login(page, base_url):
    page.goto("/manage")
    expect(page).to_have_url(base_url + "/login")
