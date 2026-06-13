from playwright.sync_api import sync_playwright


def fetch_rendered_text(url: str) -> str:
    """Fetch rendered page text via headless Chromium; raises on navigation failure or timeout."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            return page.evaluate("document.body.innerText")
        finally:
            browser.close()
