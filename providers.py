"""Product sources. Each provider returns a list of Product objects.

Providers are best-effort: if a site blocks us or changes its HTML, we log a
warning and return [] instead of crashing the agent.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("shopper.providers")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CACHE_DIR = Path(".cache")
CACHE_TTL_SECONDS = 30 * 60      # reuse a page for 30 minutes
MIN_GAP_SECONDS = 3.0            # polite delay between requests to one site
_last_request: dict[str, float] = {}


@dataclass
class Product:
    title: str
    price: float                 # current selling price in INR
    url: str
    source: str                  # "flipkart", "amazon", "demo"
    mrp: float | None = None     # list price, if shown
    rating: float | None = None
    image: str | None = None

    @property
    def discount_pct(self) -> float:
        if self.mrp and self.mrp > self.price:
            return round(100 * (self.mrp - self.price) / self.mrp, 1)
        return 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["discount_pct"] = self.discount_pct
        return d


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def polite_get(url: str, site: str) -> str | None:
    """GET with an on-disk cache and a minimum gap between requests per site."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / (re.sub(r"\W+", "_", url)[:150] + ".html")
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < CACHE_TTL_SECONDS:
        return cache_file.read_text(encoding="utf-8", errors="ignore")

    wait = MIN_GAP_SECONDS - (time.time() - _last_request.get(site, 0))
    if wait > 0:
        time.sleep(wait)
    _last_request[site] = time.time()

    for attempt in range(2):     # one retry with backoff
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"},
                timeout=15,
            )
        except requests.RequestException as exc:
            log.warning("%s request failed: %s", site, exc)
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code == 200:
            cache_file.write_text(resp.text, encoding="utf-8")
            return resp.text
        log.warning("%s returned HTTP %s", site, resp.status_code)
        if resp.status_code in (403, 429, 503):
            return None          # blocked: do not hammer
        time.sleep(2 * (attempt + 1))
    return None


class FlipkartProvider:
    name = "flipkart"

    def search(self, query: str, limit: int = 20) -> list[Product]:
        html = polite_get(f"https://www.flipkart.com/search?q={quote_plus(query)}", self.name)
        return self.parse(html, limit) if html else []

    @staticmethod
    def parse(html: str, limit: int = 20) -> list[Product]:
        # Flipkart's CSS class names are obfuscated and change often, so we rely
        # on stable things instead: data-id cards, /p/ links, img alt, rupee signs.
        soup = BeautifulSoup(html, "html.parser")
        out, seen = [], set()
        for card in soup.select("div[data-id]"):
            link = card.find("a", href=re.compile(r"/p/"))
            if not link:
                continue
            href = urljoin("https://www.flipkart.com", link["href"]).split("?")[0]
            img = link.find("img")
            title = (img.get("alt") if img else None) or link.get("title")
            prices = re.findall(r"₹\s?([\d,]+)", card.get_text(" ", strip=True))
            if not title or not prices or href in seen:
                continue
            price = _num(prices[0])
            mrp = _num(prices[1]) if len(prices) > 1 and _num(prices[1]) > price else None
            rating = re.search(r"\b([1-4]\.\d|5\.0)\b", card.get_text(" ", strip=True))
            seen.add(href)
            out.append(Product(title.strip(), price, href, "flipkart", mrp,
                               float(rating.group(1)) if rating else None,
                               img.get("src") if img else None))
            if len(out) >= limit:
                break
        return out


class AmazonProvider:
    name = "amazon"

    def search(self, query: str, limit: int = 20) -> list[Product]:
        html = polite_get(f"https://www.amazon.in/s?k={quote_plus(query)}", self.name)
        return self.parse(html, limit) if html else []

    @staticmethod
    def parse(html: str, limit: int = 20) -> list[Product]:
        soup = BeautifulSoup(html, "html.parser")
        if soup.find("form", action=re.compile("validateCaptcha")):
            log.warning("amazon asked for a CAPTCHA, skipping this source")
            return []
        out = []
        for card in soup.select("div[data-component-type='s-search-result'][data-asin]"):
            h2 = card.find("h2")
            price_el = card.select_one("span.a-price > span.a-offscreen")
            if not h2 or not price_el:
                continue
            m = re.search(r"[\d,]+(?:\.\d+)?", price_el.get_text())
            if not m:
                continue
            mrp_el = card.select_one("span.a-price.a-text-price > span.a-offscreen")
            mrp = None
            if mrp_el and (mm := re.search(r"[\d,]+(?:\.\d+)?", mrp_el.get_text())):
                mrp = _num(mm.group())
            rating_el = card.select_one("span.a-icon-alt")
            rating = None
            if rating_el and (rm := re.search(r"\d\.\d", rating_el.get_text())):
                rating = float(rm.group())
            img = card.find("img")
            price = _num(m.group())
            out.append(Product(h2.get_text(" ", strip=True), price,
                               f"https://www.amazon.in/dp/{card['data-asin']}", "amazon",
                               mrp if mrp and mrp > price else None, rating,
                               img.get("src") if img else None))
            if len(out) >= limit:
                break
        return out


class DemoProvider:
    """Offline sample catalog so the agent runs without any network access."""
    name = "demo"

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or Path(__file__).with_name("demo_catalog.json"))

    def search(self, query: str, limit: int = 20) -> list[Product]:
        if not self.path.exists():
            return []
        words = query.lower().split()
        items = json.loads(self.path.read_text())
        hits = [Product(**i) for i in items if any(w in i["title"].lower() for w in words)]
        return hits[:limit]


PROVIDERS = {"flipkart": FlipkartProvider, "amazon": AmazonProvider, "demo": DemoProvider}
