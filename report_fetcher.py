"""
report_fetcher.py
-----------------
Scrapes and parses fishing reports from:
  - On The Water (RSS feed)
  - Stripersonline forums (HTML scrape)
  - Salty Cape (RSS feed)

Returns a list of recent report dicts ready to feed into the AI scorer.
"""

import re
import requests
import feedparser
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


# ── Config ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

MAX_REPORTS     = 10   # Max reports to return total
MAX_AGE_DAYS    = 14   # Only include reports from last 14 days
MAX_TEXT_LENGTH = 600  # Truncate report body to keep Claude prompt size reasonable


# ── On The Water RSS ──────────────────────────────────────────────────────────

def fetch_on_the_water() -> list[dict]:
    """
    Parse On The Water magazine RSS feed for Cape Cod fishing reports.
    Returns list of report dicts.
    """
    # On The Water Cape Cod fishing reports tag feed
    rss_urls = [
        "https://www.onthewater.com/tag/striped-bass/feed",
        "https://www.onthewater.com/tag/cape-cod/feed",
    ]
    reports = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])

                # Skip old reports
                if pub_date and (datetime.now() - pub_date).days > MAX_AGE_DAYS:
                    continue

                # Get clean body text
                body = ""
                if hasattr(entry, "summary"):
                    soup = BeautifulSoup(entry.summary, "html.parser")
                    body = soup.get_text(separator=" ").strip()
                elif hasattr(entry, "content"):
                    soup = BeautifulSoup(entry.content[0].value, "html.parser")
                    body = soup.get_text(separator=" ").strip()

                if len(body) > MAX_TEXT_LENGTH:
                    body = body[:MAX_TEXT_LENGTH] + "..."

                reports.append({
                    "source": "On The Water",
                    "title": entry.get("title", "").strip(),
                    "date": pub_date.strftime("%Y-%m-%d") if pub_date else "unknown",
                    "url": entry.get("link", ""),
                    "body": body,
                })
        except Exception as e:
            reports.append({"source": "On The Water", "error": str(e)})

    return reports


# ── Salty Cape RSS ────────────────────────────────────────────────────────────

def fetch_salty_cape() -> list[dict]:
    """
    Parse Salty Cape Charters reports RSS / blog feed.
    """
    urls = [
        "https://www.saltycape.com/feed",
        "https://www.saltycape.com/fishing-reports/feed",
    ]
    reports = []
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])

                if pub_date and (datetime.now() - pub_date).days > MAX_AGE_DAYS:
                    continue

                body = ""
                if hasattr(entry, "summary"):
                    soup = BeautifulSoup(entry.summary, "html.parser")
                    body = soup.get_text(separator=" ").strip()

                if len(body) > MAX_TEXT_LENGTH:
                    body = body[:MAX_TEXT_LENGTH] + "..."

                reports.append({
                    "source": "Salty Cape",
                    "title": entry.get("title", "").strip(),
                    "date": pub_date.strftime("%Y-%m-%d") if pub_date else "unknown",
                    "url": entry.get("link", ""),
                    "body": body,
                })
        except Exception as e:
            reports.append({"source": "Salty Cape", "error": str(e)})

    return reports


# ── Stripersonline forums ─────────────────────────────────────────────────────

def fetch_stripersonline() -> list[dict]:
    """
    Scrape recent Cape Cod posts from Stripersonline fishing reports forum.
    This is a best-effort scrape — forum structure may change.
    Always check the site's robots.txt and ToS before scraping in production.
    """
    url = "https://www.stripersonline.com/surftalk/forum/44-cape-cod-ma/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        reports = []
        # Look for thread titles and metadata in the forum index
        threads = soup.select("h4.ipsDataItem_title a, .cForumGrid__title a")[:8]

        for thread in threads:
            title = thread.get_text(strip=True)
            link = thread.get("href", "")

            # Skip pinned/sticky threads
            if any(skip in title.lower() for skip in ["rules", "sticky", "welcome", "announcement"]):
                continue

            # Try to fetch the first post of each thread for body text
            body = _fetch_thread_first_post(link)

            reports.append({
                "source": "Stripersonline",
                "title": title,
                "date": "recent",
                "url": link,
                "body": body,
            })

        return reports[:4]  # Limit to 4 from this source to avoid overloading the prompt

    except Exception as e:
        return [{"source": "Stripersonline", "error": str(e)}]


def _fetch_thread_first_post(url: str) -> str:
    """Fetch the first post body from a Stripersonline thread."""
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        post = soup.select_one(".cPost_contentWrap, .ipsType_normal")
        if post:
            text = post.get_text(separator=" ").strip()
            return text[:MAX_TEXT_LENGTH] + ("..." if len(text) > MAX_TEXT_LENGTH else "")
        return ""
    except Exception:
        return ""


# ── Manual / user-submitted reports ──────────────────────────────────────────

def get_manual_reports() -> list[dict]:
    """
    Placeholder for user-submitted on-the-water reports.
    In production this would query your database.
    For the prototype, return a hardcoded example to test the pipeline.
    """
    return [
        {
            "source": "User report",
            "title": "Chatham Inlet — good bite this morning",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "url": "",
            "body": (
                "Hit the Chatham rips at first light on the outgoing tide. "
                "Water was 58°F and clear. Had 4 fish between 28–36 inches in about 2 hours. "
                "All on SP Minnow white/chartreuse. Lots of bird activity over the rip. "
                "Bait is definitely moving through — saw bunker schools."
            ),
        }
    ]


# ── Main aggregator ───────────────────────────────────────────────────────────

def get_all_reports(include_manual: bool = True) -> list[dict]:
    """
    Fetch reports from all sources and return a combined, deduplicated list.
    Filters out error entries and truncates to MAX_REPORTS.
    """
    print("Fetching On The Water reports...")
    reports = fetch_on_the_water()

    print("Fetching Salty Cape reports...")
    reports += fetch_salty_cape()

    print("Fetching Stripersonline reports...")
    reports += fetch_stripersonline()

    if include_manual:
        print("Loading manual/user reports...")
        reports += get_manual_reports()

    # Filter out error-only entries
    valid = [r for r in reports if "error" not in r or r.get("body")]

    # Deduplicate by title
    seen_titles = set()
    deduped = []
    for r in valid:
        title_key = r.get("title", "").lower().strip()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            deduped.append(r)

    return deduped[:MAX_REPORTS]


if __name__ == "__main__":
    import json
    reports = get_all_reports()
    print(f"\nFetched {len(reports)} reports:\n")
    for r in reports:
        print(f"  [{r['source']}] {r.get('title', 'No title')} ({r.get('date', '?')})")
        if r.get("body"):
            print(f"    {r['body'][:120]}...")
        print()
