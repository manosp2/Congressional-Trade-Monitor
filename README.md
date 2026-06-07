# Congressional Trade Monitor

A Flask dashboard that monitors public congressional trade disclosures from Capitol Trades and sends polished email alerts for the latest filing.

## Features

- Clean dashboard for the latest public disclosure
- In-memory caching to reduce rate limits from the source site
- One-click email alert from the web UI with a Gmail-friendly HTML layout
- Optional background polling mode from `ins.py`
- Secret configuration through a local `.env` file

## Positioning

This project is framed as a public-data monitoring and alerting system. It demonstrates web scraping, defensive error handling, caching, environment-based configuration, Flask routing, responsive UI work, and transactional email delivery.

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your local environment file:

```bash
cp .env.example .env
```

Fill in `.env` with your own values. For Gmail, use an app password instead of your normal account password.

## Run The Dashboard

```bash
python app.py
```

Open `http://localhost:5001`.

The default local app port is controlled by `APP_PORT` in `.env`.
Displayed refresh timestamps are controlled by `DISPLAY_TIMEZONE`.

## Run Background Monitoring

```bash
python ins.py
```

The polling interval is controlled by `CHECK_INTERVAL_SECONDS`.

## Rate Limits

Capitol Trades can return `429 Too Many Requests` if the app refreshes too often. The dashboard caches the latest successful scrape for `CACHE_SECONDS` seconds, which defaults to 15 minutes. Increase this value in `.env` if you still hit rate limits.

## Security Notes

`.env` is ignored by Git, so future local credentials should not be committed.

If credentials were already committed, deleting them from the current file is not enough before making the repository public. Git history can still expose old commits. Rotate the leaked Gmail app password immediately, then either keep the repo private or rewrite the repository history with a tool such as `git filter-repo` or BFG Repo-Cleaner before publishing.
