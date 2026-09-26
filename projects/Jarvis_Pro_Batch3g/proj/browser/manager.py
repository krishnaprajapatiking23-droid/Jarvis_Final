"""
Browser Manager — automates and extracts information from web browsers.

Supported:
  - Selenium WebDriver (Chrome, Firefox, Edge) — full browser automation
  - Requests-based scraping (no browser needed)

Install Selenium:
    pip install selenium webdriver-manager
"""

import platform
import subprocess
import time
from threading import Lock
from typing import Dict, List, Optional


_SYSTEM = platform.system()


class BrowserManager:

    def __init__(self):
        self._driver = None
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Selenium WebDriver
    # ------------------------------------------------------------------

    def _get_driver(self, browser: str = "chrome"):
        """Lazy-load a Selenium WebDriver instance."""
        if self._driver:
            return self._driver

        try:
            from selenium import webdriver
            if browser == "chrome":
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    from selenium.webdriver.chrome.service import Service
                    opts = webdriver.ChromeOptions()
                    opts.add_argument("--headless")
                    self._driver = webdriver.Chrome(
                        service=Service(
                            ChromeDriverManager().install()),
                        options=opts)
                except Exception:
                    opts = webdriver.ChromeOptions()
                    opts.add_argument("--headless")
                    self._driver = webdriver.Chrome(options=opts)
            elif browser == "firefox":
                from selenium.webdriver.firefox.options import Options
                opts = Options()
                opts.add_argument("--headless")
                self._driver = webdriver.Firefox(options=opts)
            return self._driver
        except ImportError:
            raise ImportError(
                "selenium not installed — run: pip install selenium webdriver-manager")

    def open(self, url: str, browser: str = "chrome") -> Dict:
        """Open a URL in the specified browser."""
        try:
            driver = self._get_driver(browser)
            driver.get(url)
            title = driver.title
            return {
                "success": True,
                "url": url,
                "title": title,
                "browser": browser,
            }
        except ImportError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search(self, query: str, browser: str = "chrome") -> Dict:
        """Open a Google search for the given query."""
        import urllib.parse
        q = urllib.parse.quote_plus(query)
        return self.open(f"https://www.google.com/search?q={q}", browser)

    def get_page_text(self, url: str, browser: str = "chrome") -> str:
        """Fetch visible text from a page using Selenium."""
        try:
            driver = self._get_driver(browser)
            driver.get(url)
            time.sleep(2)  # allow JS to render
            return driver.page_source[:5000]
        except Exception as e:
            return f"Error: {e}"

    def click_element(self, selector: str, by: str = "css") -> Dict:
        """Click a page element by CSS selector or XPath."""
        if not self._driver:
            return {"success": False, "error": "No active browser — call open() first"}
        try:
            from selenium.webdriver.common.by import By
            by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH,
                      "id": By.ID, "class": By.CLASS_NAME}
            element = self._driver.find_element(by_map.get(by, By.CSS_SELECTOR),
                                                selector)
            element.click()
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fill_form(self, selector: str, value: str,
                  submit: bool = False, by: str = "css") -> Dict:
        """Fill an input field and optionally submit."""
        if not self._driver:
            return {"success": False, "error": "No active browser"}
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH,
                      "id": By.ID, "name": By.NAME}
            elem = self._driver.find_element(
                by_map.get(by, By.CSS_SELECTOR), selector)
            elem.clear()
            elem.send_keys(value)
            if submit:
                elem.send_keys(Keys.RETURN)
            return {"success": True, "selector": selector, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close(self) -> Dict:
        """Close the current browser session."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
        return {"success": True}

    # ------------------------------------------------------------------
    # Headless HTTP fetch (no browser needed)
    # ------------------------------------------------------------------

    def fetch(self, url: str, headers: dict = None) -> Dict:
        """Fetch a URL using urllib (no Selenium)."""
        try:
            import urllib.request
            req = urllib.request.Request(url)
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {
                    "success": True,
                    "status_code": resp.status,
                    "headers": dict(resp.headers),
                    "body": resp.read(1024 * 100).decode("utf-8", errors="replace"),
                }
        except Exception as e:
            return {"success": False, "error": str(e)}


_manager = BrowserManager()

open_url = _manager.open
search = _manager.search
get_page_text = _manager.get_page_text
click_element = _manager.click_element
fill_form = _manager.fill_form
close = _manager.close
fetch = _manager.fetch
