from unittest.mock import MagicMock, patch


def _make_playwright_mock(inner_text: str):
    mock_page = MagicMock()
    mock_page.evaluate.return_value = inner_text

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_p)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    return mock_ctx, mock_page, mock_browser


def test_fetch_rendered_text_returns_inner_text():
    mock_ctx, mock_page, mock_browser = _make_playwright_mock("Hello from the page")

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        result = fetch_rendered_text("https://example.com")

    assert result == "Hello from the page"


def test_fetch_rendered_text_navigates_to_url():
    mock_ctx, mock_page, _ = _make_playwright_mock("content")

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        fetch_rendered_text("https://example.com/path")

    mock_page.goto.assert_called_once_with(
        "https://example.com/path", wait_until="networkidle", timeout=30000
    )


def test_fetch_rendered_text_closes_browser():
    mock_ctx, _, mock_browser = _make_playwright_mock("content")

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        fetch_rendered_text("https://example.com")

    mock_browser.close.assert_called_once()


def test_fetch_rendered_text_closes_browser_on_error():
    mock_page = MagicMock()
    mock_page.goto.side_effect = Exception("Navigation failed")

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_p)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        try:
            fetch_rendered_text("https://example.com")
        except Exception:
            pass

    mock_browser.close.assert_called_once()
