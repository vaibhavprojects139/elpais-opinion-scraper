import os
import re
import sys
import time
import json
import threading
import argparse
import requests
from io import BytesIO
from collections import Counter
from urllib.parse import urljoin
from pathlib import Path
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)

load_dotenv()

ELPAIS_URL = "https://elpais.com"
OPINION_URL = "https://elpais.com/opinion/"
IMAGES_DIR = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)

BS_USERNAME = os.getenv("BROWSERSTACK_USERNAME", "YOUR_BS_USERNAME")
BS_ACCESS_KEY = os.getenv("BROWSERSTACK_ACCESS_KEY", "YOUR_BS_ACCESS_KEY")
BS_HUB_URL = f"https://{BS_USERNAME}:{BS_ACCESS_KEY}@hub-cloud.browserstack.com/wd/hub"

RAPID_API_KEY = os.getenv("RAPID_API_KEY", "")         # RapidAPI key for translation
GOOGLE_TRANSLATE_KEY = os.getenv("GOOGLE_TRANSLATE_KEY", "")  # Or Google Translate API key

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "that", "this", "it", "its", "as", "from", "have", "has", "had", "will",
    "would", "could", "should", "may", "might", "can", "do", "does", "did",
    "not", "no", "so", "if", "than", "then", "about", "into", "through",
    "during", "before", "after", "above", "below", "between", "out", "off",
    "up", "down", "over", "under", "again", "further", "their", "they",
    "them", "these", "those", "what", "which", "who", "whom", "how", "when",
    "where", "why", "all", "both", "each", "few", "more", "most", "other",
    "some", "such", "own", "same", "just"
}

BS_CAPABILITIES = [
    {
        "browserName": "Chrome",
        "browserVersion": "latest",
        "bstack:options": {
            "os": "Windows",
            "osVersion": "11",
            "sessionName": "ElPais-Chrome-Win11",
            "projectName": "El Pais Assignment",
            "buildName": "ElPais Opinion Scraper",
        },
    },
    {
        "browserName": "Firefox",
        "browserVersion": "latest",
        "bstack:options": {
            "os": "OS X",
            "osVersion": "Ventura",
            "sessionName": "ElPais-Firefox-MacVentura",
            "projectName": "El Pais Assignment",
            "buildName": "ElPais Opinion Scraper",
        },
    },
    {
        "browserName": "Edge",
        "browserVersion": "latest",
        "bstack:options": {
            "os": "Windows",
            "osVersion": "10",
            "sessionName": "ElPais-Edge-Win10",
            "projectName": "El Pais Assignment",
            "buildName": "ElPais Opinion Scraper",
        },
    },
    {
        "browserName": "Chrome",
        "bstack:options": {
            "deviceName": "Samsung Galaxy S23",
            "osVersion": "13.0",
            "realMobile": "true",
            "sessionName": "ElPais-Chrome-Android",
            "projectName": "El Pais Assignment",
            "buildName": "ElPais Opinion Scraper",
        },
    },
    {
        "browserName": "Safari",
        "bstack:options": {
            "deviceName": "iPhone 14",
            "osVersion": "16",
            "realMobile": "true",
            "sessionName": "ElPais-Safari-iPhone14",
            "projectName": "El Pais Assignment",
            "buildName": "ElPais Opinion Scraper",
        },
    },
]




def translate_with_rapidapi(text: str) -> str:
    """Translate Spanish → English using RapidAPI multi-translation endpoint."""
    url = "https://rapid-translate-multi-traduction.p.rapidapi.com/t"
    headers = {
        "content-type": "application/json",
        "X-RapidAPI-Key": RAPID_API_KEY,
        "X-RapidAPI-Host": "rapid-translate-multi-traduction.p.rapidapi.com",
    }
    payload = {"from": "es", "to": "en", "q": text}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if isinstance(result, list) and result:
            return result[0]
        return result.get("translated", text)
    except Exception as exc:
        print(f"  [RapidAPI error] {exc}")
        return text


def translate_with_google(text: str) -> str:
    """Translate Spanish → English using Google Cloud Translate REST API."""
    url = "https://translation.googleapis.com/language/translate/v2"
    params = {"q": text, "source": "es", "target": "en", "key": GOOGLE_TRANSLATE_KEY}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()["data"]["translations"][0]["translatedText"]
    except Exception as exc:
        print(f"  [Google Translate error] {exc}")
        return text


def translate_free_fallback(text: str) -> str:
    """
    Zero-key fallback using the unofficial Google Translate endpoint.
    Good for demos / local runs where no API key is configured.
    """
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "es",
        "tl": "en",
        "dt": "t",
        "q": text,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return "".join(chunk[0] for chunk in data[0] if chunk[0])
    except Exception as exc:
        print(f"  [Free translation error] {exc}")
        return text


def translate(text: str) -> str:
    """Route translation through whichever API is configured."""
    if RAPID_API_KEY:
        return translate_with_rapidapi(text)
    if GOOGLE_TRANSLATE_KEY:
        return translate_with_google(text)
    return translate_free_fallback(text)


# ─── Image Download Helper ──────────────────────────────────────────────────────

def download_image(url: str, filename: str) -> bool:
    """Download an image from URL and save to IMAGES_DIR."""
    try:
        resp = requests.get(url, timeout=15, stream=True)
        resp.raise_for_status()
        save_path = IMAGES_DIR / filename
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  ✓ Image saved: {save_path}")
        return True
    except Exception as exc:
        print(f"  ✗ Image download failed: {exc}")
        return False




def set_spanish_language(driver: webdriver.Remote) -> None:
    """
    Ensure the site is served in Spanish by:
    1. Adding lang=es query param if needed.
    2. Accepting a cookie/language modal when it appears.
    """
    driver.get(OPINION_URL)
    wait = WebDriverWait(driver, 15)

    
    for selector in [
        "button#didomi-notice-agree-button",
        "button[data-testid='accept-all-btn']",
        "button.pmConsentWall-btn",
        "button[aria-label='Aceptar']",
    ]:
        try:
            btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            btn.click()
            time.sleep(1)
            break
        except TimeoutException:
            pass


    try:
        lang = driver.find_element(By.TAG_NAME, "html").get_attribute("lang")
        if lang and lang.startswith("es"):
            print(f"  ✓ Page language confirmed: {lang}")
        else:
            print(f"  ⚠ Page lang attribute: '{lang}' — expected 'es'")
    except NoSuchElementException:
        pass


def scrape_articles(driver: webdriver.Remote) -> list[dict]:
    """
    Scrape first 5 articles from the Opinion section.
    Returns a list of dicts with keys: title, content, image_url, article_url.
    """
    wait = WebDriverWait(driver, 20)
    articles = []

 
    EXCLUDED_PATHS = [
        "/opinion/", "/opinion/editoriales/", "/opinion/tribunas/",
        "/opinion/columnas/", "/opinion/el-debate/", "/opinion/cartas/"
    ]

    def is_real_article(url):
        """Return True only for individual article URLs, not section index pages."""
        if not url or "elpais.com" not in url:
            return False
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path
            if "/opinion/" not in path:
                return False
            for excl in EXCLUDED_PATHS:
                if path.rstrip("/") == excl.rstrip("/"):
                    return False
         
            path_parts = [p for p in path.split("/") if p]
            return len(path_parts) >= 3
        except Exception:
            return False

    article_links = []
    seen = set()

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2 a, h3 a")))
        headline_links = driver.find_elements(By.CSS_SELECTOR, "h2 a, h3 a, h4 a")
        for el in headline_links:
            try:
                href = el.get_attribute("href")
                if href and href not in seen and is_real_article(href):
                    seen.add(href)
                    article_links.append(href)
            except Exception:
                continue
            if len(article_links) >= 5:
                break
    except Exception:
        pass

    if len(article_links) < 5:
        all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/opinion/']")
        for el in all_links:
            try:
                href = el.get_attribute("href")
                if href and href not in seen and is_real_article(href):
                    seen.add(href)
                    article_links.append(href)
            except Exception:
                continue
            if len(article_links) >= 5:
                break

    print(f"\n  Found {len(article_links)} article links. Scraping first 5...\n")

    for idx, url in enumerate(article_links[:5], start=1):
        try:
            driver.get(url)
            wait = WebDriverWait(driver, 15)

         
            try:
                title_el = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "h1.a-ti, h1.article-title, h1[class*='title'], h1")
                    )
                )
                title = title_el.text.strip()
            except TimeoutException:
                title = "N/A"

         
            content_parts = []
            for selector in ["div.a-body p", "div[data-dtm-region='articulo_cuerpo'] p",
                              "article p", "div.article-body p"]:
                paragraphs = driver.find_elements(By.CSS_SELECTOR, selector)
                if paragraphs:
                    content_parts = [p.text.strip() for p in paragraphs if p.text.strip()]
                    break
            content = "\n".join(content_parts[:6]) if content_parts else "Content not available"

   
            image_url = None
            for img_selector in [
                "figure.a-fi img", "div.a-header-image img",
                "figure img", "picture source[type='image/jpeg']",
                "article img"
            ]:
                try:
                    img_el = driver.find_element(By.CSS_SELECTOR, img_selector)
                    src = img_el.get_attribute("src") or img_el.get_attribute("data-src")
                    if src and src.startswith("http"):
                        image_url = src
                        break
                except NoSuchElementException:
                    continue

            article = {
                "index": idx,
                "title": title,
                "content": content,
                "image_url": image_url,
                "article_url": url,
            }
            articles.append(article)


            if image_url:
                ext = image_url.split(".")[-1].split("?")[0][:4] or "jpg"
                safe_title = re.sub(r"[^\w]", "_", title[:40])
                download_image(image_url, f"article_{idx}_{safe_title}.{ext}")
            else:
                print(f"  ⚠ No cover image for article {idx}")

        except Exception as exc:
            print(f"  ✗ Error scraping article {idx} ({url}): {exc}")

    return articles


def print_articles(articles: list[dict]) -> None:
    """Pretty-print scraped article data in Spanish."""
    separator = "═" * 70
    print(f"\n{separator}")
    print("  ARTÍCULOS SCRAPEADOS — EL PAÍS / OPINIÓN")
    print(separator)
    for article in articles:
        print(f"\n[{article['index']}] {article['title']}")
        print(f"    URL: {article['article_url']}")
        print(f"\n    Contenido:")
        for line in article["content"].split("\n")[:4]:
            print(f"      {line}")
        print()


def translate_and_print_headers(articles: list[dict]) -> list[str]:
    """Translate each article title to English and print."""
    print("\n" + "═" * 70)
    print("  TRANSLATED HEADERS (Spanish → English)")
    print("═" * 70)
    translated = []
    for article in articles:
        en_title = translate(article["title"])
        translated.append(en_title)
        print(f"\n  [{article['index']}] ES: {article['title']}")
        print(f"       EN: {en_title}")
    return translated


def analyze_word_frequency(translated_headers: list[str]) -> None:
    """Print words repeated more than twice across all translated headers."""
    print("\n" + "═" * 70)
    print("  WORD FREQUENCY ANALYSIS (words repeated > 2 times)")
    print("═" * 70)

    all_words = []
    for header in translated_headers:
        words = re.findall(r"\b[a-zA-Z]{3,}\b", header.lower())
        all_words.extend(w for w in words if w not in STOP_WORDS)

    freq = Counter(all_words)
    repeated = {word: count for word, count in freq.items() if count > 2}

    if repeated:
        print(f"\n  {'Word':<25} {'Count':>6}")
        print(f"  {'-'*25} {'-'*6}")
        for word, count in sorted(repeated.items(), key=lambda x: -x[1]):
            print(f"  {word:<25} {count:>6}")
    else:
        print("\n  No words repeated more than twice across all headers.")
        print("\n  Full word frequency (for reference):")
        for word, count in freq.most_common(10):
            print(f"  {word:<25} {count:>6}")




def get_local_driver() -> webdriver.Chrome:
    """Return a local Chrome driver with Spanish locale settings."""
    options = ChromeOptions()
    options.add_argument("--lang=es")
    options.add_argument("--accept-lang=es-ES,es;q=0.9")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,800")
    options.add_experimental_option(
        "prefs", {"intl.accept_languages": "es,es-ES"}
    )
    return webdriver.Chrome(options=options)


def get_browserstack_driver(capabilities: dict) -> webdriver.Remote:
    """Return a Remote WebDriver pointing at BrowserStack hub."""
    options = ChromeOptions()
    options.set_capability("bstack:options", capabilities.get("bstack:options", {}))

    browser = capabilities.get("browserName", "Chrome").lower()
    if browser == "firefox":
        options = FirefoxOptions()
        options.set_capability("bstack:options", capabilities.get("bstack:options", {}))

    caps = {
        "browserName": capabilities.get("browserName", "Chrome"),
        "browserVersion": capabilities.get("browserVersion", "latest"),
        "bstack:options": capabilities.get("bstack:options", {}),
    }

    driver = webdriver.Remote(
        command_executor=BS_HUB_URL,
        options=options,
    )
    # Inject full capabilities
    driver.capabilities.update(caps)
    return driver




def run_scrape(driver: webdriver.Remote, thread_id: int = 0) -> None:
    """
    Full pipeline: navigate → scrape → translate → analyze.
    Designed to run identically in local and BrowserStack contexts.
    """
    tag = f"[Thread-{thread_id}]" if thread_id else "[Local]"
    try:
        print(f"\n{tag} Setting up Spanish language session...")
        set_spanish_language(driver)

        print(f"{tag} Scraping articles...")
        articles = scrape_articles(driver)

        if not articles:
            print(f"{tag} ✗ No articles scraped.")
            return

        print_articles(articles)
        translated = translate_and_print_headers(articles)
        analyze_word_frequency(translated)

        
        output_path = f"results_thread_{thread_id}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"\n{tag} ✓ Results saved to {output_path}")

    except WebDriverException as exc:
        print(f"{tag} ✗ WebDriver error: {exc}")
    finally:
        driver.quit()


def run_local() -> None:
    """Single-threaded local run for validation."""
    print("\n" + "=" * 70)
    print("  LOCAL RUN — Chrome")
    print("=" * 70)
    driver = get_local_driver()
    run_scrape(driver, thread_id=0)


def run_browserstack_thread(cap_set: dict, thread_id: int) -> None:
    """Single BrowserStack thread target."""
    session = cap_set.get("bstack:options", {}).get("sessionName", f"Thread-{thread_id}")
    print(f"\n[Thread-{thread_id}] Starting BrowserStack session: {session}")
    try:
        driver = get_browserstack_driver(cap_set)
        run_scrape(driver, thread_id)
        driver.execute_script(
            'browserstack_executor: {"action": "setSessionStatus", '
            '"arguments": {"status": "passed", "reason": "Scrape completed"}}'
        )
    except Exception as exc:
        print(f"[Thread-{thread_id}] ✗ Session failed: {exc}")
        try:
            driver.execute_script(
                f'browserstack_executor: {{"action": "setSessionStatus", '
                f'"arguments": {{"status": "failed", "reason": "{str(exc)[:100]}"}}}}'
            )
            driver.quit()
        except Exception:
            pass


def run_browserstack_parallel() -> None:
    """Launch 5 parallel BrowserStack sessions."""
    print("\n" + "=" * 70)
    print("  BROWSERSTACK PARALLEL RUN — 5 Threads")
    print("=" * 70)
    threads = []
    for idx, cap_set in enumerate(BS_CAPABILITIES, start=1):
        t = threading.Thread(
            target=run_browserstack_thread,
            args=(cap_set, idx),
            name=f"BS-Thread-{idx}",
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\n✓ All BrowserStack sessions complete.")




def parse_args():
    parser = argparse.ArgumentParser(
        description="El País Opinion Scraper — Local & BrowserStack"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--local", action="store_true",
                       help="Run locally with Chrome WebDriver")
    group.add_argument("--browserstack", action="store_true",
                       help="Run on BrowserStack with 5 parallel threads")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.browserstack:
        run_browserstack_parallel()
    else:
        run_local()