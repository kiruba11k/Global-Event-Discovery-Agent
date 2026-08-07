"""
ExhibitionsVoice trade-show scraper — all countries.

Scrapes https://exhibitionsvoice.com/trade-shows/country/<slug> page by page,
country by country. For each listing page it visits every event's detail page,
extracts the full event data, and APPENDS the rows to that country's CSV
before moving on to the next listing page — so progress is saved
incrementally. When one country is finished it moves to the next country,
each saved in a different CSV (e.g. usa_trade_shows.csv,
china_trade_shows.csv, ...).

Usage:
    pip install requests beautifulsoup4
    python exhibitionsvoice_usa_scraper.py                     # all countries
    python exhibitionsvoice_usa_scraper.py --country usa       # one country
    python exhibitionsvoice_usa_scraper.py --country usa --start 3
    python exhibitionsvoice_usa_scraper.py --from-country india # resume list from India

Output: one CSV per country in --outdir (default: current directory).
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
REQUEST_DELAY = 1.5  # seconds between requests, be polite
TIMEOUT = 30

# Country slugs in scrape order (as listed on exhibitionsvoice.com)
COUNTRIES = [
    "usa",
    "china",
    "brazil",
    "indonesia",
    "germany",
    "india",
    "australia",
    "france",
    "united-kingdom",
    "thailand",
    "singapore",
    "vietnam",
    "cambodia",
    "malaysia",
    "mexico",
    "colombia",
    "united-arab-emirates",
    "taiwan",
    "saudi-arabia",
    "kenya",
    "south-korea",
    "switzerland",
    "japan",
    "philippines",
    "canada",
    "turkey",
    "peru",
    "netherlands",
    "egypt",
    "sweden",
    "italy",
    "russia",
    "tanzania",
    "kazakhstan",
    "belgium",
    "austria",
    "south-africa",
    "pakistan",
    "argentina",
    "spain",
    "ghana",
    "portugal",
    "hong-kong-sar-china",
    "syria",
    "iran",
    "panama",
    "macau",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

FIELDNAMES = [
    "country",
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


def scrape_country(slug, start=1, end=None, outdir="."):
    """Scrape one country hub, page by page, into its own CSV."""
    hub_url = f"{BASE_URL}/trade-shows/country/{slug}"
    csv_path = os.path.join(outdir, f"{slug.replace('-', '_')}_trade_shows.csv")

    already_scraped = load_scraped_urls(csv_path)
    if already_scraped:
        print(f"Resuming {slug}: {len(already_scraped)} events already in {csv_path}")

    print(f"\n########## Country: {slug} ##########")
    print(f"Fetching hub page: {hub_url}")
    first_soup = get_soup(f"{hub_url}?slug={slug}&page={start}")
    if first_soup is None:
        print(f"Could not load hub page for {slug}; skipping country.")
        return

    total_pages = get_total_pages(first_soup)
    last_page = min(end, total_pages) if end else total_pages
    print(f"Total pages detected: {total_pages}; scraping pages {start}–{last_page}")

    page = start
    soup = first_soup
    while page <= last_page:
        if soup is None:
            soup = get_soup(f"{hub_url}?slug={slug}&page={page}")
            if soup is None:
                print(f"Skipping page {page} (could not load).")
                page += 1
                continue

        events = parse_listing_page(soup)
        print(f"\n=== {slug} — Page {page}: {len(events)} events ===")

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
            data["country"] = slug
            data["page"] = page
            if not data["event_name"]:
                data["event_name"] = title
            rows.append(data)
            already_scraped.add(url)

        # Save this page's data BEFORE moving to the next page
        if rows:
            append_rows(rows, csv_path)
            print(f"  -> Saved {len(rows)} rows to {csv_path}")

        page += 1
        soup = None
        if page <= last_page:
            time.sleep(REQUEST_DELAY)

    print(f"Finished {slug}. Data stored in {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape ExhibitionsVoice trade shows for all countries"
    )
    parser.add_argument("--country", help="scrape only this country slug (e.g. usa)")
    parser.add_argument(
        "--from-country",
        help="start the full country list from this slug (skip earlier ones)",
    )
    parser.add_argument("--start", type=int, default=1, help="page to start from")
    parser.add_argument("--end", type=int, default=None, help="page to stop at (inclusive)")
    parser.add_argument("--outdir", default=".", help="directory for the output CSVs")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    if args.country:
        countries = [args.country]
    else:
        countries = COUNTRIES
        if args.from_country:
            if args.from_country not in countries:
                sys.exit(f"Unknown country slug: {args.from_country}")
            countries = countries[countries.index(args.from_country):]

    print(f"Countries to scrape: {', '.join(countries)}")
    for slug in countries:
        scrape_country(slug, start=args.start, end=args.end, outdir=args.outdir)
        time.sleep(REQUEST_DELAY)

    print("\nAll countries done.")


if __name__ == "__main__":
    main()
