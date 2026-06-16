"""
Job hunt alert for internships / MTO / graduate / entry-level roles in Bangladesh.
Uses DuckDuckGo for search (no API key, no signup, no billing).

Modes (set by MODE env var in the workflow):
  "daily"  : send only NEW postings since last run
  "weekly" : send EVERYTHING currently found (full sweep, ignores memory)

Required environment variables (GitHub Secrets):
  GREENAPI_INSTANCE
  GREENAPI_TOKEN
  WHATSAPP_NUMBER   (digits only, e.g. 8801XXXXXXXXX)
Optional:
  MODE             ("daily" default, or "weekly")
"""

import os
import sys
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from ddgs import DDGS

GREENAPI_INSTANCE = os.environ["GREENAPI_INSTANCE"]
GREENAPI_TOKEN = os.environ["GREENAPI_TOKEN"]
WHATSAPP_NUMBER = os.environ["WHATSAPP_NUMBER"]
MODE = os.environ.get("MODE", "daily").lower()

SEEN_FILE = "seen_jobs.json"
BDT = timezone(timedelta(hours=6))
MAX_CHARS_PER_MESSAGE = 3500
MAX_ITEMS = 60
RESULTS_PER_QUERY = 8

QUERIES = [
    'internship Bangladesh 2026 business finance marketing',
    'intern Dhaka 2026',
    'management trainee Bangladesh 2026',
    'graduate trainee programme Bangladesh 2026',
    'Unilever ULIP UFLP Bangladesh',
    'BAT Bangladesh global graduate',
    'Nestle Marico Reckitt management trainee Bangladesh',
    'bKash Grameenphone Standard Chartered graduate trainee Bangladesh',
    'fresh graduate entry level finance marketing Dhaka 2026',
    'bdjobs management trainee intern 2026',
    'nextjobz intern graduate Bangladesh',
]

RELEVANCE_WORDS = [
    "intern", "internship", "trainee", "mto", "graduate", "ulip", "uflp",
    "fresh", "entry level", "entry-level", "early career", "junior",
    "management trainee", "fresher",
]
EXCLUDE_WORDS = [
    "india", "pakistan", "5+ years", "senior manager", "10+ years",
]


def search_all():
    found = {}
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                for r in ddgs.text(q, region="xa-en", max_results=RESULTS_PER_QUERY):
                    title = (r.get("title") or "").strip()
                    link = (r.get("href") or "").strip()
                    body = (r.get("body") or "")
                    if not link:
                        continue
                    text = (title + " " + body).lower()
                    if any(b in text for b in EXCLUDE_WORDS):
                        continue
                    if not any(w in text for w in RELEVANCE_WORDS):
                        continue
                    key = link.split("?")[0].rstrip("/").lower()
                    if key not in found:
                        found[key] = {"title": title, "link": link}
            except Exception as e:
                print(f"Search failed for [{q}]: {e}")
            time.sleep(1.0)  # be gentle, reduce rate-limiting
    return found


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=1)


def norm(link):
    return link.split("?")[0].rstrip("/").lower()


def send_whatsapp(text):
    url = (
        f"https://api.green-api.com/waInstance{GREENAPI_INSTANCE}"
        f"/sendMessage/{GREENAPI_TOKEN}"
    )
    payload = json.dumps({"chatId": f"{WHATSAPP_NUMBER}@c.us", "message": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("Green API response:", resp.read().decode())
    time.sleep(1.5)


def send_in_chunks(header, jobs):
    blocks = [f"{i}. {j['title']}\n{j['link']}" for i, j in enumerate(jobs, 1)]
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
    found = search_all()
    items = list(found.values())[:MAX_ITEMS]

    if MODE == "weekly":
        if not items:
            print("Weekly sweep found nothing.")
            return
        header = f"*Weekly job sweep* ({today}) - {len(items)} roles:"
        send_in_chunks(header, items)
        save_seen({norm(j["link"]) for j in items})
        print(f"Weekly: sent {len(items)}.")
        return

    seen = load_seen()
    new_items = [j for j in items if norm(j["link"]) not in seen]
    for j in new_items:
        seen.add(norm(j["link"]))
    save_seen(seen)

    if not new_items:
        print("No new postings today, no message sent.")
        return
    header = f"*New job alerts* ({today}) - {len(new_items)} new:"
    send_in_chunks(header, new_items)
    print(f"Daily: sent {len(new_items)} new.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Failed:", e)
        sys.exit(1)
