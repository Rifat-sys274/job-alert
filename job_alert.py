"""
Daily job alert for MTO / internship / graduate programme openings in Bangladesh.
Searches Google (Programmable Search API), remembers what it already sent,
and WhatsApps you only the NEW postings each morning.

Required environment variables (GitHub Secrets):
  GOOGLE_API_KEY     - from Google Cloud Console (Custom Search API enabled)
  GOOGLE_CSE_ID      - your Programmable Search Engine ID (cx)
  GREENAPI_INSTANCE  - same as your World Cup bot
  GREENAPI_TOKEN     - same as your World Cup bot
  WHATSAPP_NUMBER    - same as your World Cup bot, digits only
"""

import os
import sys
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
GOOGLE_CSE_ID = os.environ["GOOGLE_CSE_ID"]
GREENAPI_INSTANCE = os.environ["GREENAPI_INSTANCE"]
GREENAPI_TOKEN = os.environ["GREENAPI_TOKEN"]
WHATSAPP_NUMBER = os.environ["WHATSAPP_NUMBER"]

SEEN_FILE = "seen_jobs.json"
MAX_ITEMS_PER_DAY = 15
BDT = timezone(timedelta(hours=6))

# Edit these freely. Each line is one Google search, restricted to the last 7 days.
QUERIES = [
    '"management trainee" Bangladesh 2026',
    '"graduate programme" OR "graduate program" Bangladesh 2026',
    'Unilever ULIP OR UFLP Bangladesh',
    'BAT Bangladesh "global graduate"',
    'Nestle OR Marico OR Reckitt "management trainee" Bangladesh',
    'site:bdjobs.com "management trainee" OR intern',
    'site:linkedin.com/jobs "management trainee" Bangladesh',
    'bKash OR Grameenphone OR "Standard Chartered" graduate trainee Bangladesh',
]

# A result must contain at least one of these words (title or snippet)
RELEVANCE_WORDS = [
    "trainee", "intern", "graduate", "mto", "ulip", "uflp",
    "fresh", "entry level", "early career",
]


def google_search(query):
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(
        {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": 10,
            "gl": "bd",
            "dateRestrict": "d7",  # only results indexed in the last 7 days
        }
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data.get("items", [])
    except Exception as e:
        print(f"Search failed for [{query}]: {e}")
        return []


def is_relevant(title, snippet):
    text = (title + " " + snippet).lower()
    return any(w in text for w in RELEVANCE_WORDS)


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=1)


def normalize(link):
    # strip tracking params so the same job isn't "new" twice
    return link.split("?")[0].rstrip("/").lower()


def send_whatsapp(text):
    url = (
        f"https://api.green-api.com/waInstance{GREENAPI_INSTANCE}"
        f"/sendMessage/{GREENAPI_TOKEN}"
    )
    payload = json.dumps(
        {"chatId": f"{WHATSAPP_NUMBER}@c.us", "message": text}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("Green API response:", resp.read().decode())


def main():
    seen = load_seen()
    new_items = []
    for q in QUERIES:
        for item in google_search(q):
            link = item.get("link", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            key = normalize(link)
            if not link or key in seen:
                continue
            if not is_relevant(title, snippet):
                continue
            seen.add(key)
            new_items.append({"title": title.strip(), "link": link})

    save_seen(seen)

    today = datetime.now(BDT).strftime("%d %b %Y")
    if not new_items:
        print("No new postings today, no message sent.")
        return

    shown = new_items[:MAX_ITEMS_PER_DAY]
    lines = [f"*New job alerts* ({today}):", ""]
    for i, job in enumerate(shown, 1):
        lines.append(f"{i}. {job['title']}")
        lines.append(job["link"])
        lines.append("")
    if len(new_items) > MAX_ITEMS_PER_DAY:
        lines.append(f"(+{len(new_items) - MAX_ITEMS_PER_DAY} more, showing top {MAX_ITEMS_PER_DAY})")

    send_whatsapp("\n".join(lines).strip())
    print(f"Sent {len(shown)} new postings.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Failed:", e)
        sys.exit(1)
