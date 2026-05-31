# Signal — AI × Design Intelligence Platform

Your personal weekly briefing on AI and product design, auto-generated every Monday and hosted live on Vercel.

---

## Setup (one-time, ~15 minutes)

### 1. Push to GitHub
```bash
cd signal-platform
git init
git add .
git commit -m "init: signal platform"
# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/signal-platform.git
git push -u origin main
```

### 2. Add your Claude API key to GitHub Secrets
1. Go to your repo on GitHub → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your key from [console.anthropic.com](https://console.anthropic.com)

### 3. Deploy to Vercel
1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Import your GitHub repo
3. Framework preset: **Other** (it's a static site)
4. Root directory: `/` (default)
5. Click **Deploy**

Vercel auto-deploys every time GitHub Actions pushes new week data. ✅

---

## How it works

```
Every Monday 8am UTC
        ↓
GitHub Actions runs fetch_weekly.py
        ↓
Fetches 8 live RSS sources simultaneously
        ↓
Claude API scores each article (relevance to product designers)
        ↓
Writes data/weeks/YYYY-WNN.json  +  updates data/archive.json
        ↓
Commits to GitHub → Vercel auto-deploys in ~30 seconds
        ↓
Your live site updates with the new week's panel
```

---

## File structure

```
signal-platform/
├── index.html              ← Single-page app (all 4 views)
├── vercel.json             ← Vercel routing config
├── data/
│   ├── archive.json        ← Index of all weeks
│   └── weeks/
│       ├── 2025-W26.json   ← Each week's full data
│       ├── 2025-W25.json
│       └── ...
├── scripts/
│   ├── fetch_weekly.py     ← The automation script
│   └── requirements.txt
└── .github/
    └── workflows/
        └── weekly.yml      ← Cron job (every Monday 8am)
```

---

## Each week's archive URL

Every past week is accessible at a permanent URL:
```
https://your-site.vercel.app/?week=2025-W26
https://your-site.vercel.app/?week=2025-W25
```

---

## Run manually (test before Monday)
```bash
cd signal-platform
pip install -r scripts/requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python scripts/fetch_weekly.py
```

---

## Estimated cost
~$1–3/month in Claude API usage at this volume (52 articles × weekly scoring).
