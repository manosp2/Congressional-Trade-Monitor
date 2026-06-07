import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Flask, redirect, render_template, request, url_for

from ins import (
    EmailConfigError,
    EmailSendError,
    TradeRateLimitError,
    get_recent_trades,
    send_email,
)

app = Flask(__name__)

APP_PORT = int(os.getenv("APP_PORT", "5001"))
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "900"))
DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "Europe/Amsterdam")

trade_cache = {
    "trades": None,
    "fetched_at": None,
    "error": None,
}


def display_timezone():
    try:
        return ZoneInfo(DISPLAY_TIMEZONE)
    except Exception:
        return timezone.utc


def format_checked_at(value):
    if not value:
        value = datetime.now(timezone.utc)

    local_time = value.astimezone(display_timezone())
    return local_time.strftime("%Y-%m-%d %H:%M %Z")


def get_cached_trades(force_refresh=False):
    now = datetime.now(timezone.utc)
    cached_trades = trade_cache["trades"]
    fetched_at = trade_cache["fetched_at"]

    if cached_trades and fetched_at and not force_refresh:
        cache_age = now - fetched_at
        if cache_age < timedelta(seconds=CACHE_SECONDS):
            return cached_trades, fetched_at, None, True

    try:
        trades = get_recent_trades(limit=30)
    except TradeRateLimitError as exc:
        trade_cache["error"] = str(exc)
        if cached_trades:
            return cached_trades, fetched_at, str(exc), True
        return [], now, str(exc), False
    except Exception as exc:
        trade_cache["error"] = str(exc)
        if cached_trades:
            return cached_trades, fetched_at, str(exc), True
        return [], now, str(exc), False

    trade_cache["trades"] = trades
    trade_cache["fetched_at"] = now
    trade_cache["error"] = None
    return trades, now, None, False

@app.route("/")
def index():
    email_status = request.args.get("email_status")
    email_error = request.args.get("email_error")
    trades, fetched_at, error, using_cache = get_cached_trades()
    data = trades[0] if trades else {}

    return render_template(
        "index.html",
        data=data,
        trades=trades,
        email_status=email_status,
        email_error=email_error,
        error=error,
        last_checked=fetched_at or datetime.now(timezone.utc),
        last_checked_label=format_checked_at(fetched_at),
        using_cache=using_cache,
        cache_seconds=CACHE_SECONDS,
    )


@app.post("/send-email")
def email():
    trades, _, error, _ = get_cached_trades()
    data = trades[0] if trades else {}

    if error and not data:
        return redirect(url_for("index", email_status="source_failed"))

    try:
        send_email(data)
        return redirect(url_for("index", email_status="sent"))
    except (EmailConfigError, EmailSendError) as exc:
        return redirect(
            url_for("index", email_status="failed", email_error=str(exc))
        )
    except Exception as exc:
        return redirect(
            url_for(
                "index",
                email_status="failed",
                email_error=f"Unexpected email error: {exc}",
            )
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
