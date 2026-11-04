"""Collect recent entries from configured official RSS/Atom release feeds."""
import json, os, feedparser
from pathlib import Path
from datetime import datetime, timezone, timedelta
from calendar import timegm
from dotenv import load_dotenv
load_dotenv()

def collect(feed_file=None, days=None):
    path = Path(feed_file or os.getenv("RELEASE_FEEDS_JSON", "release_feeds.json"))
    feeds = json.loads(path.read_text(encoding="utf-8"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(days or os.getenv("RELEASE_LOOKBACK_DAYS", "7")))
    output, errors = [], []
    for technology, urls in feeds.items():
        for url in urls:
            parsed = feedparser.parse(url)
            if parsed.bozo and not parsed.entries:
                errors.append({"technology": technology, "feed": url, "error": str(parsed.bozo_exception)})
            for entry in parsed.entries:
                stamp = entry.get("published_parsed") or entry.get("updated_parsed")
                published_utc = datetime.fromtimestamp(timegm(stamp), timezone.utc) if stamp else None
                if published_utc and published_utc < cutoff: continue
                output.append({"technology": technology, "title": entry.get("title", "Untitled release"),
                    "url": entry.get("link", url), "published": entry.get("published", entry.get("updated", "Unknown")),
                    "summary": entry.get("summary", "")[:1500], "published_utc": published_utc.isoformat() if published_utc else None,
                    "source_feed": url})
    output.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    return {"lookback_days": int(days or os.getenv("RELEASE_LOOKBACK_DAYS", "7")), "items": output, "feed_errors": errors}
