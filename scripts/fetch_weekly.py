#!/usr/bin/env python3
"""
Signal Platform — Weekly Fetcher
Runs every Monday via GitHub Actions.
Fetches live RSS sources, scores with Claude API, generates week JSON.
"""

import os
import json
import feedparser
import anthropic
from datetime import datetime, timedelta
from isoweek import Week
import hashlib

# ─── CONFIG ─────────────────────────────────────────────────────────────────

SOURCES = {
    "investors": [
        {"name": "a16z", "url": "https://a16z.com/feed/", "icon": "💰"},
    ],
    "education": [
        {"name": "Nielsen Norman Group", "url": "https://www.nngroup.com/feed/rss/", "icon": "🎓"},
        {"name": "UX Collective",        "url": "https://uxdesign.cc/feed",           "icon": "🎓"},
    ],
    "architecture": [
        {"name": "Dezeen",               "url": "https://www.dezeen.com/feed/",        "icon": "🏛️"},
    ],
    "policy": [
        {"name": "Wired",                "url": "https://www.wired.com/feed/rss",      "icon": "⚖️"},
    ],
    "media": [
        {"name": "The Verge",            "url": "https://www.theverge.com/rss/index.xml", "icon": "🎬"},
        {"name": "TechCrunch",           "url": "https://techcrunch.com/feed/",        "icon": "🎬"},
    ],
    "healthcare": [
        {"name": "MIT Tech Review",      "url": "https://www.technologyreview.com/feed/", "icon": "🏥"},
    ],
}

# Only articles published in the last 8 days
LOOKBACK_DAYS = 8

# How many stories to pick per field
TOP_PER_FIELD = 2

# ─── HELPERS ────────────────────────────────────────────────────────────────

def get_week_id():
    now = datetime.utcnow()
    w = now.isocalendar()
    return f"{w[0]}-W{w[1]:02d}"

def get_week_meta():
    now = datetime.utcnow()
    w = now.isocalendar()
    week_obj = Week(w[0], w[1])
    start = week_obj.monday().strftime("%b %-d")
    end   = week_obj.sunday().strftime("%-d, %Y")
    return {
        "weekId":    f"{w[0]}-W{w[1]:02d}",
        "week":      w[1],
        "year":      w[0],
        "dateRange": f"{start}–{end}",
    }

def fetch_source(source, field, cutoff):
    """Fetch an RSS feed and return recent entries."""
    try:
        feed = feedparser.parse(source["url"])
        items = []
        for entry in feed.entries[:30]:
            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])
            else:
                published = datetime.utcnow()

            if published < cutoff:
                continue

            summary = getattr(entry, "summary", "") or ""
            # Strip HTML tags simply
            import re
            summary = re.sub(r"<[^>]+>", "", summary)[:500]

            items.append({
                "id":      hashlib.md5(entry.link.encode()).hexdigest()[:12],
                "title":   entry.title,
                "url":     entry.link,
                "summary": summary,
                "source":  source["name"],
                "field":   field,
                "icon":    source["icon"],
                "published": published.isoformat(),
            })
        return items
    except Exception as e:
        print(f"  ⚠ Error fetching {source['name']}: {e}")
        return []

def score_articles(articles, client):
    """Use Claude to score and enrich articles for product designers."""
    if not articles:
        return []

    prompt = f"""You are curating a weekly intelligence briefing for a product design student who wants to track cutting-edge AI and design news.

For each article below, score its relevance to product designers (0-10) and provide:
- A 2-3 sentence summary (use <strong> for key facts/numbers)
- A 1-2 sentence "Why it matters for you" (speak directly to a product design student)
- A practical "Get started" tip (specific, actionable, under 40 words)

Only return articles with score >= 6. Return as JSON array with fields:
id, score (float), summary, whyItMatters, tip

Articles:
{json.dumps([{"id": a["id"], "title": a["title"], "summary": a["summary"], "url": a["url"]} for a in articles], indent=2)}

Return ONLY valid JSON array. No markdown, no explanation."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        import re
        text = response.content[0].text.strip()
        # Extract JSON if wrapped in markdown
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            scored = json.loads(match.group())
        else:
            scored = json.loads(text)

        # Merge scores back into articles
        score_map = {s["id"]: s for s in scored}
        enriched = []
        for a in articles:
            if a["id"] in score_map:
                s = score_map[a["id"]]
                enriched.append({**a, **s})
        return sorted(enriched, key=lambda x: x.get("score", 0), reverse=True)
    except Exception as e:
        print(f"  ⚠ Could not parse Claude response: {e}")
        return []

def pick_must_watch(client, week_signals):
    """Ask Claude to pick/generate the best study resource for the week."""
    titles = [s["source"] + ": " + s.get("summary","")[:100] for s in week_signals[:5]]
    prompt = f"""Based on this week's top design + AI topics:
{chr(10).join(titles)}

Recommend ONE real, specific online resource (article, video, or course) that a product design student should read/watch this week.
Return JSON: {{ "title": "...", "channel": "...", "channelIcon": "🎨", "url": "https://...", "duration": "...", "tip": "..." }}
Only return JSON."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        import re
        text = response.content[0].text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(match.group()) if match else None
    except:
        return None

# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    meta   = get_week_meta()
    week_id = meta["weekId"]

    print(f"\n🔍 Signal Weekly Fetch — {week_id} ({meta['dateRange']})")
    print("=" * 60)

    # ── 1. Fetch all sources
    all_articles = []
    for field, sources in SOURCES.items():
        for source in sources:
            print(f"  Fetching {source['name']} ({field})…")
            articles = fetch_source(source, field, cutoff)
            print(f"    → {len(articles)} recent articles")
            all_articles.extend(articles)

    print(f"\n📥 Total articles fetched: {len(all_articles)}")

    # ── 2. Score with Claude, field by field
    field_buckets = {}
    for a in all_articles:
        field_buckets.setdefault(a["field"], []).append(a)

    top_signals = []
    for field, articles in field_buckets.items():
        print(f"\n🤖 Scoring {field} ({len(articles)} articles)…")
        scored = score_articles(articles[:15], client)  # cap to avoid huge prompts
        top = scored[:TOP_PER_FIELD]
        print(f"    → {len(top)} selected")
        top_signals.extend(top)

    top_signals.sort(key=lambda x: x.get("score", 0), reverse=True)

    # ── 3. Pick must-watch
    print("\n📺 Picking must-watch resource…")
    must_watch = pick_must_watch(client, top_signals)
    if not must_watch:
        must_watch = {
            "title": "Designing AI Products & Features — Study Guide",
            "channel": "Nielsen Norman Group",
            "channelIcon": "🎓",
            "url": "https://www.nngroup.com/articles/designing-ai-study-guide/",
            "duration": "Study guide",
            "tip": "The most comprehensive free resource on AI UX. Start with the AI Agents module."
        }

    # ── 4. Build agent updates (top 4 tool-related stories)
    tool_stories = [s for s in top_signals if any(
        kw in (s.get("title","") + s.get("summary","")).lower()
        for kw in ["figma", "claude", "cursor", "framer", "openai", "gemini", "tool", "launch", "feature", "update"]
    )][:4]

    agent_updates = [{
        "name": s["source"] + " — " + s["title"][:50],
        "description": (s.get("summary","")[:120]).replace("<strong>","").replace("</strong>",""),
        "tag": s["source"].split()[0],
        "url": s["url"]
    } for s in tool_stories]

    if not agent_updates:
        agent_updates = [{
            "name": "Figma AI — Weekly Updates",
            "description": "Latest AI features in Figma design tools",
            "tag": "Figma",
            "url": "https://www.figma.com/blog/"
        }]

    # ── 5. Assemble week JSON
    week_data = {
        **meta,
        "headline": top_signals[0]["title"] if top_signals else "This Week in AI Design",
        "stats": {
            "storiesScanned": len(all_articles),
            "topPicks": len(top_signals),
            "newTools": len(tool_stories),
            "activity": [35, 60, 45, 80, 55, 100, 50]
        },
        "signals": [{
            "id":           s["id"],
            "source":       s["source"],
            "field":        s["field"],
            "fieldLabel":   s["field"].replace("media", "Media & Tech").replace("policy", "Policy & Law")
                             .replace("investors","Investors").replace("architecture","Architecture")
                             .replace("healthcare","Healthcare").replace("education","Education").title(),
            "icon":         s["icon"],
            "score":        round(s.get("score", 7.0), 1),
            "url":          s["url"],
            "summary":      s.get("summary", s.get("title","")),
            "whyItMatters": s.get("whyItMatters", ""),
            "tip":          s.get("tip", "")
        } for s in top_signals],
        "agentUpdates":  agent_updates,
        "mustWatch":     must_watch
    }

    # ── 6. Write week JSON
    out_path = f"data/weeks/{week_id}.json"
    os.makedirs("data/weeks", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(week_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Week data written → {out_path}")

    # ── 7. Update archive index
    archive_path = "data/archive.json"
    with open(archive_path) as f:
        archive = json.load(f)

    # Check if this week already exists
    existing_ids = [w["weekId"] for w in archive["weeks"]]
    if week_id not in existing_ids:
        top4 = [s["title"] for s in top_signals[:4]]
        archive["weeks"].insert(0, {
            "weekId":    week_id,
            "week":      meta["week"],
            "year":      meta["year"],
            "dateRange": meta["dateRange"],
            "headline":  week_data["headline"],
            "stats":     week_data["stats"],
            "topStories": top4
        })

    archive["current"] = week_id

    with open(archive_path, "w") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)
    print(f"✅ Archive updated → {archive_path}")
    print(f"\n🚀 Week {meta['week']} ready — {len(top_signals)} signals, {len(all_articles)} stories scanned\n")

if __name__ == "__main__":
    main()
