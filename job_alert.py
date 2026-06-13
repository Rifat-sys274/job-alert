"""
Job hunt alert for internships / MTO / graduate / entry-level roles in Bangladesh.

Two modes (controlled by the MODE env var the workflow sets):
  - "daily"  : send only NEW postings since last run (quiet on slow days)
  - "weekly" : send EVERYTHING currently open (full sweep, ignores memory)

Required environment variables (GitHub Secrets):
  GOOGLE_API_KEY     - Google Cloud, Custom Search API enabled
  GOOGLE_CSE_ID      - Programmable Search Engine ID (cx)
  GREENAPI_INSTANCE  - same as before
  GREENAPI_TOKEN     - same as before
  WHATSAPP_NUMBER    - digits only, e.g. 8801XXXXXXXXX
Optional:
  MODE               - "daily" (default) or "weekly"
"""

import os
import sys
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
GOOGLE_CSE_ID = os.environ["GOOGLE_CSE_ID"]
GREENAPI_INSTANCE = os.environ["GREENAPI_INSTANCE"]
GREENAPI_TOKEN = os.environ["GREENAPI_TOKEN"]
WHATSAPP_NUMBER = os.environ["WHATSAPP_NUMBER"]
MODE = os.environ.get("MODE", "daily").lower()

SEEN_FILE = "seen_jobs.json"
BDT = timezone(timedelta(hours=6))

MAX_CHARS_PER_MESSAGE = 3500
MAX_ITEMS = 60

QUERIES = [
    'internship Bangladesh 2026 business OR finance OR marketing',
    '"intern" Dhaka 2026 -unpaid',
    'site:bdjobs.com intern 2026',
    'site:linkedin.com/jobs internship Bangladesh',
    'site:nextjobz.com.bd intern OR internship',
    '"management trainee" Bangladesh 2026',
    '"graduate programme" OR "graduate program" OR "graduate trainee" Bangladesh 2026',
    'Unilever ULIP OR UFLP Bangladesh',
    'BAT Bangladesh "global graduate"',
    'Nestle OR Marico OR Reckitt OR "L\'Oreal" "management trainee" Bangladesh',
    'bKash OR Grameenphone OR Robi OR "Standard Chartered" OR HSBC graduate trainee Bangladesh',
    'site:bdjobs.com "fresh graduate" OR "entry level" 2026',
    'site:skill.jobs management trainee OR intern OR graduate',
    '"entry level" OR "fresh graduate" finance OR marketing Dhaka 2026',
    'site:linkedin.com/jobs "entry level" Bangladesh business',
]

RELEVANCE_WORDS = [
    "intern", "internship", "trainee", "mto", "graduate", "ulip", "uflp",
    "fresh", "entry level", "entry-level", "early career", "junior",
    "management trainee", "fresher",
]

EXCLUDE_WORDS = [
    "india", "pakistan", "experienced only", "5+ years", "senior manager",
]


def google_search(query, want_recent):
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": 10,
        "gl": "bd",
    }
    if want_recent:
        params["dateRestrict"] = "d7"
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data.get("items", [])
    except Exception as e:
        print(f"Search failed for [{query}]: {e}")
        return []


def is_relevant(title, snippet):
    text = (title + " " + snippet).lower()
    if any(bad in text for bad in EXCLUDE_WORDS):
        return False
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
    return link.split("?")[0].rstrip("/").lower()


def collect():
    want_recent = (MODE == "daily")
    found = {}
    for q in QUERIES:
        for item in google_search(q, want_recent):
            link = item.get("link", "")
            title = item.get("title", "").strip()
            snippet = item.get("snippet", "")
            if not link or not is_relevant(title, snippet):
                continue
            key = normalize(link)
            if key not in found:
                found[key] = {"title": title, "link": link}
        time.sleep(0.3)
    return found


def send_whatsapp(text):
    url = (
        f"https://api.green-api.com/waInstance{GREENAPI_INSTANCE}"
        f"/sendMessage/{GREENAPI_TOKEN}"
    )
    payload = json.dumps({"chatId": f"{WHATSAPP_NUMBER}@c.us", "message": text}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("Green API response:", resp.read().decode())
    time.sleep(1.5)


def send_in_chunks(header, jobs):
    blocks = []
    for i, job in enumerate(jobs, 1):
        blocks.append(f"{i}. {job['title']}\n{job['link']}")

    current = header + "\n\n"
    part = 1
    for block in blocks:
        if len(current) + len(block) + 2 > MAX_CHARS_PER_MESSAGE:
            send_whatsapp(current.strip())
            part += 1
            current = f"(continued, part {part})\n\n"
        current += block + "\n\n"
    if current.strip():
        send_whatsapp(current.strip())


def main():
    today = datetime.now(BDT).strftime("%d %b %Y")
    found = collect()
    items = list(found.values())[:MAX_ITEMS]

    if MODE == "weekly":
        if not items:
            print("Weekly sweep found nothing.")
            return
        header = f"*Weekly job sweep* ({today}) - {len(items)} open roles:"
        send_in_chunks(header, items)
        save_seen({normalize(j["link"]) for j in items})
        print(f"Weekly: sent {len(items)} roles.")
        return

    seen = load_seen()
    new_items = [j for j in items if normalize(j["link"]) not in seen]
    for j in new_items:
        seen.add(normalize(j["link"]))
    save_seen(seen)

    if not new_items:
        print("No new postings today, no message sent.")
        return
    header = f"*New job alerts* ({today}) - {len(new_items)} new:"
    send_in_chunks(header, new_items)
    print(f"Daily: sent {len(new_items)} new postings.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Failed:", e)
        sys.exit(1)
