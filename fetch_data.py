#!/usr/bin/env python3
"""
fetch_data.py — reads subreddits.psv, fetches top posts from each,
saves everything to data.json for the HTML reader to load.

Run: python3 fetch_data.py
Runs server-side (GitHub Actions, terminal, Termux) — no CORS issues.

pip install requests
"""

import json, time, random, csv, os, requests
from datetime import datetime, timezone

PSV_FILE   = "subreddits.psv"
OUT_FILE   = "data.json"
SORT       = "hot"          # hot | top | new
TIME_FILTER= "day"          # only used when SORT=top
LIMIT      = 25             # posts per subreddit
DELAY_MIN  = 1.2            # seconds between requests (min)
DELAY_MAX  = 3.0            # seconds between requests (max)

HEADERS = {
    "User-Agent": "Mozilla/5.0 NLFeedBot/1.0 (noncommercial archival; +https://github.com/nlfeed)"
}

def load_subreddits():
    subs = []
    with open(PSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            subs.append(row)
    return subs

def fetch_sub(subreddit, sort=SORT, limit=LIMIT):
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    params = {"limit": limit, "raw_json": 1}
    if sort == "top":
        params["t"] = TIME_FILTER
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code == 404:
            print(f"  ✗ r/{subreddit} — 404 not found, skipping")
            return []
        if r.status_code == 403:
            print(f"  ✗ r/{subreddit} — 403 blocked")
            return []
        if r.status_code == 429:
            print(f"  ✗ r/{subreddit} — 429 rate limited, waiting 30s...")
            time.sleep(30)
            return fetch_sub(subreddit, sort, limit)  # retry once
        r.raise_for_status()
        posts = r.json()["data"]["children"]
        return [p["data"] for p in posts]
    except Exception as e:
        print(f"  ✗ r/{subreddit} — {e}")
        return []

def clean_post(post, meta):
    """Extract only what the HTML reader needs — keep payload small."""
    img = None
    if post.get("preview"):
        try:
            img = post["preview"]["images"][0]["source"]["url"].replace("&amp;", "&")
        except:
            pass
    if not img and post.get("thumbnail", "").startswith("http"):
        img = post["thumbnail"]
    if not img and post.get("url", "").lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        img = post["url"]

    return {
        "id":          post.get("id"),
        "title":       post.get("title", "")[:300],
        "author":      post.get("author", ""),
        "sub":         post.get("subreddit", meta["subreddit"]),
        "score":       post.get("score", 0),
        "comments":    post.get("num_comments", 0),
        "created_utc": post.get("created_utc", 0),
        "permalink":   post.get("permalink", ""),
        "url":         post.get("url", ""),
        "is_self":     post.get("is_self", False),
        "selftext":    post.get("selftext", "")[:300],
        "img":         img,
        "nsfw":        post.get("over_18", False),
        # metadata from PSV
        "category":    meta.get("category", ""),
        "country":     meta.get("country", ""),
        "type":        meta.get("type", ""),
    }

def run():
    print(f"\n{'═'*55}")
    print(f"  NLFeed data fetch  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*55}\n")

    subs = load_subreddits()
    print(f"Loaded {len(subs)} subreddits from {PSV_FILE}\n")

    all_posts = []
    ok = 0
    fail = 0

    for i, meta in enumerate(subs):
        sub = meta["subreddit"]
        print(f"[{i+1:02d}/{len(subs)}] r/{sub} ({meta['category']}, {meta['country']})")

        posts = fetch_sub(sub)
        if posts:
            cleaned = [clean_post(p, meta) for p in posts]
            all_posts.extend(cleaned)
            print(f"       ✓ {len(cleaned)} posts")
            ok += 1
        else:
            fail += 1

        # Random delay between requests
        if i < len(subs) - 1:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            time.sleep(delay)

    # Deduplicate by post id
    seen = set()
    unique_posts = []
    for p in all_posts:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique_posts.append(p)

    # Sort by score descending (default view)
    unique_posts.sort(key=lambda p: p["score"], reverse=True)

    output = {
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "fetched_at_human": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
        "subreddits_ok":   ok,
        "subreddits_fail": fail,
        "total_posts": len(unique_posts),
        "posts": unique_posts,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(OUT_FILE) // 1024
    print(f"\n{'═'*55}")
    print(f"  Done!")
    print(f"  {ok} subreddits OK, {fail} failed")
    print(f"  {len(unique_posts)} unique posts saved to {OUT_FILE} ({size_kb} KB)")
    print(f"{'═'*55}\n")

if __name__ == "__main__":
    run()
