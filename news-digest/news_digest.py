import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "24"))
MAX_ITEMS_PER_FEED = int(os.environ.get("MAX_ITEMS_PER_FEED", "5"))

logging.basicConfig(
    filename=BASE_DIR / "news_digest.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

TAG_RE = re.compile(r"<[^<]+?>")


def load_feeds():
    with open(BASE_DIR / "feeds.json", "r", encoding="utf-8") as f:
        return json.load(f)


def parse_entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def summarize(entry):
    text = entry.get("summary", "") or entry.get("description", "")
    text = TAG_RE.sub("", text).strip()
    if len(text) > 200:
        text = text[:200].rsplit(" ", 1)[0] + "..."
    return text


DEDUP_SUFFIX_RE = re.compile(r"\([가-힣0-9]*보\)\s*$")
LEADING_TAG_RE = re.compile(r"^\[[^\]]*\]\s*")


def dedup_key(title, aggressive=False):
    key = LEADING_TAG_RE.sub("", title)
    key = DEDUP_SUFFIX_RE.sub("", key).strip()
    if aggressive:
        key = key.split(",")[0].strip()
    return key


def collect_category(urls, keywords=None):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items = []
    seen = set()
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logging.warning("Feed failed: %s (%s)", url, feed.bozo_exception)
                continue
            count = 0
            for entry in feed.entries:
                pub = parse_entry_time(entry)
                if pub and pub < cutoff:
                    continue
                title = entry.get("title", "(제목 없음)")
                if keywords and not any(kw in title for kw in keywords):
                    continue
                key = dedup_key(title, aggressive=bool(keywords))
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        "title": title,
                        "link": entry.get("link", ""),
                        "summary": summarize(entry),
                    }
                )
                count += 1
                if count >= MAX_ITEMS_PER_FEED:
                    break
        except Exception:
            logging.exception("Error fetching feed %s", url)
    return items


def build_message(sections):
    today = datetime.now().strftime("%Y-%m-%d (%a)")
    lines = [f"*🗞 {today} 아침 뉴스 브리핑*"]
    for name, items in sections.items():
        if not items:
            continue
        lines.append(f"\n*━━ {name} ━━*")
        for item in items:
            lines.append(f"• [{item['title']}]({item['link']})")
            if item["summary"]:
                lines.append(f"  _{item['summary']}_")
    if len(lines) == 1:
        lines.append("\n_새로운 뉴스가 없습니다._")
    return "\n".join(lines)


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID가 설정되지 않았습니다 (.env 확인)")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    max_len = 3500
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)

    for chunk in chunks:
        resp = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            logging.error("Telegram send failed: %s", resp.text)
            resp.raise_for_status()


def main():
    feeds = load_feeds()
    sections = {}
    for category, cfg in feeds.items():
        sections[category] = collect_category(cfg["sources"], cfg.get("keywords"))
    message = build_message(sections)
    send_telegram(message)
    logging.info("Digest sent successfully (%d chars)", len(message))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Digest run failed")
        raise
