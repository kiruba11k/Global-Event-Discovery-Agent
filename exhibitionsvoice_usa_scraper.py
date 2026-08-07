"""
ExhibitionsVoice USA trade-show scraper.

Scrapes https://exhibitionsvoice.com/trade-shows/country/usa page by page.
For each listing page it visits every event's detail page, extracts the full
event data, and APPENDS the rows to the CSV before moving on to the next
listing page — so progress is saved incrementally.

Usage:
    pip install requests beautifulsoup4
    python exhibitionsvoice_usa_scraper.py            # scrape all pages
    python exhibitionsvoice_usa_scraper.py --start 3  # resume from page 3

Output: usa_trade_shows.csv
"""

import argparse
import csv
import os
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://exhibitionsvoice.com"
HUB_URL = BASE_URL + "/trade-shows/country/usa"
OUTPUT_CSV = "usa_trade_shows.csv"
REQUEST_DELAY = 1.5  # seconds between requests, be polite
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

FIELDNAMES = [
    "page",
    "event_name",
    "event_url",
    "event_type",
    "description",
    "dates",
    "city_country",
    "industries",
    "organizer",
    "organizer_website",
    "organizer_email",
    "contact_email",
    "venue_name",
    "venue_address",
    "official_site",
    "overview",
    "image_url",
]

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url):
    """Fetch a URL with retries and return a BeautifulSoup object."""
    for attempt in range(4):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            wait = 2 ** (attempt + 1)
            print(f"  ! Request failed ({exc}); retrying in {wait}s...")
            time.sleep(wait)
    print(f"  !! Giving up on {url}")
    return None


def text_or_empty(node):
    return node.get_text(" ", strip=True) if node else ""


def parse_listing_page(soup):
    """Return list of (title, absolute_url) for events on a hub listing page."""
    events = []
    for a in soup.select("ul.hub-event-list a.hub-event-list-item"):
        href = a.get("href", "")
        if not href.startswith("/event/"):
            continue
        title_node = a.select_one(".hub-event-list-title")
        title = text_or_empty(title_node) or a.get("title", "").strip()
        events.append((title, urljoin(BASE_URL, href)))
    return events


def get_total_pages(soup):
    """Find highest page number in the pagination links."""
    pages = [1]
    for a in soup.select("nav.ev-pagination a.page-link"):
        m = re.search(r"[?&]page=(\d+)", a.get("href", ""))
        if m:
            pages.append(int(m.group(1)))
        elif a.get_text(strip=True).isdigit():
            pages.append(int(a.get_text(strip=True)))
    return max(pages)


def parse_event_page(url):
    """Scrape one event detail page into a dict."""
    soup = get_soup(url)
    if soup is None:
        return None

    data = {key: "" for key in FIELDNAMES}
    data["event_url"] = url

    data["event_name"] = text_or_empty(soup.select_one("h1.event-banner-title"))
    data["event_type"] = text_or_empty(soup.select_one("p.event-profile-eyebrow"))
    data["description"] = text_or_empty(
        soup.select_one("p.event-aeo-lead[itemprop='description']")
        or soup.select_one("header p.event-aeo-lead")
    )

    # Meta chips: location, industries, organizer
    industries = []
    for chip in soup.select(".event-meta-chips .event-meta-chip"):
        icon = chip.select_one("i")
        cls = " ".join(icon.get("class", [])) if icon else ""
        txt = text_or_empty(chip)
        if "map-marked" in cls or "map-marker" in cls:
            data["city_country"] = txt
        elif "industry" in cls:
            industries.append(txt)
        elif "building" in cls:
            data["organizer"] = txt
    data["industries"] = "; ".join(industries)

    # Sidebar facts: dates + venue
    for fact in soup.select(".event-sidebar-fact"):
        label = text_or_empty(fact.select_one(".event-sidebar-fact-label")).lower()
        value = text_or_empty(fact.select_one(".event-sidebar-fact-value"))
        if "date" in label:
            data["dates"] = value
        elif "venue" in label:
            data["venue_address"] = value

    # Venue section
    data["venue_name"] = text_or_empty(soup.select_one(".event-venue-name"))
    street = text_or_empty(soup.select_one(".event-venue-street"))
    if street:
        data["venue_address"] = street

    # Official site link
    official = soup.select_one(
        ".event-profile-actions a.event-btn-outline[href^='http']"
    ) or soup.select_one(".event-sidebar-actions a[href^='http']")
    if official:
        data["official_site"] = official.get("href", "")

    # Emails
    mails = [
        a.get("href", "")[7:]
        for a in soup.select("a[href^='mailto:']")
        if "@" in a.get("href", "") and "?" not in a.get("href", "")
    ]
    if mails:
        data["contact_email"] = mails[0]

    # Organizer card
    org = soup.select_one(".event-sidebar-org")
    if org:
        name = text_or_empty(org.select_one("strong"))
        if name:
            data["organizer"] = name
        site = org.select_one(".event-sidebar-org-links a[href^='http']")
        if site:
            data["organizer_website"] = site.get("href", "")
        mail = org.select_one(".event-sidebar-org-links a[href^='mailto:']")
        if mail:
            data["organizer_email"] = mail.get("href", "")[7:]

    # Overview paragraph from the About section
    data["overview"] = text_or_empty(
        soup.select_one("#section-overview p") or soup.select_one("#event-about p")
    )

    img = soup.select_one(".event-hero-image img")
    if img:
        data["image_url"] = img.get("src", "")

    return data


def append_rows(rows, csv_path):
    """Append rows to the CSV, writing the header if the file is new."""
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def load_scraped_urls(csv_path):
    """URLs already in the CSV so a resumed run skips them."""
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return {row.get("event_url", "") for row in csv.DictReader(f)}


def main():
    parser = argparse.ArgumentParser(description="Scrape ExhibitionsVoice USA trade shows")
    parser.add_argument("--start", type=int, default=1, help="page to start from")
    parser.add_argument("--end", type=int, default=None, help="page to stop at (inclusive)")
    parser.add_argument("--out", default=OUTPUT_CSV, help="output CSV path")
    args = parser.parse_args()

    already_scraped = load_scraped_urls(args.out)
    if already_scraped:
        print(f"Resuming: {len(already_scraped)} events already in {args.out}")

    print(f"Fetching hub page: {HUB_URL}")
    first_soup = get_soup(f"{HUB_URL}?slug=usa&page={args.start}")
    if first_soup is None:
        sys.exit("Could not load the hub page.")

    total_pages = get_total_pages(first_soup)
    last_page = min(args.end, total_pages) if args.end else total_pages
    print(f"Total pages detected: {total_pages}; scraping pages {args.start}–{last_page}")

    page = args.start
    soup = first_soup
    while page <= last_page:
        if soup is None:
            soup = get_soup(f"{HUB_URL}?slug=usa&page={page}")
            if soup is None:
                print(f"Skipping page {page} (could not load).")
                page += 1
                continue

        events = parse_listing_page(soup)
        print(f"\n=== Page {page}: {len(events)} events ===")

        rows = []
        for i, (title, url) in enumerate(events, 1):
            if url in already_scraped:
                print(f"  [{i}/{len(events)}] SKIP (already scraped): {title}")
                continue
            print(f"  [{i}/{len(events)}] {title}")
            time.sleep(REQUEST_DELAY)
            data = parse_event_page(url)
            if data is None:
                continue
            data["page"] = page
            if not data["event_name"]:
                data["event_name"] = title
            rows.append(data)
            already_scraped.add(url)

        # Save this page's data BEFORE moving to the next page
        if rows:
            append_rows(rows, args.out)
            print(f"  -> Saved {len(rows)} rows to {args.out}")

        page += 1
        soup = None
        if page <= last_page:
            time.sleep(REQUEST_DELAY)

    print(f"\nDone. Data stored in {args.out}")


if __name__ == "__main__":
    main()
