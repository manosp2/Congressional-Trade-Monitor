import os
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from html import escape

import requests
import certifi
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TRADE_URL = os.getenv("TRADE_URL", "https://www.capitoltrades.com/trades")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", "Congressional Trade Monitor")
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "1800"))

TRADE_COLUMNS = [
    "Politician",
    "Trade Issuer",
    "Published",
    "Traded",
    "Filed After",
    "Owner",
    "Type",
    "Size",
    "Price",
]

SOURCE_DATE_FORMATS = ("%d %b %Y", "%b %d, %Y", "%Y-%m-%d")


class TradeRateLimitError(RuntimeError):
    pass


class EmailConfigError(RuntimeError):
    pass


class EmailSendError(RuntimeError):
    pass


def fetch_trade_document():
    response = requests.get(
        TRADE_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
        },
        timeout=20,
    )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        message = "Capitol Trades is rate limiting requests. Try again later."
        if retry_after:
            message += f" Retry after: {retry_after} seconds."
        raise TradeRateLimitError(message)

    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_trade_row(row):
    cells = row.find_all("td")
    if len(cells) < len(TRADE_COLUMNS):
        return None

    return {
        column: cells[index].get_text(" ", strip=True)
        for index, column in enumerate(TRADE_COLUMNS)
    }


def get_recent_trades(limit=30):
    doc = fetch_trade_document()
    table = doc.find("table")
    if table is None:
        raise ValueError("Could not find a trades table on the source page.")

    rows = table.find_all("tr")
    if len(rows) < 2:
        raise ValueError("The trades table did not contain any trade rows.")

    trades = []
    for row in rows[1 : limit + 1]:
        parsed = parse_trade_row(row)
        if parsed:
            trades.append(parsed)

    if not trades:
        raise ValueError("The trades table did not contain parseable trade rows.")

    return trades


def get_latest_trade():
    return get_recent_trades(limit=1)[0]


def parse_source_date(value):
    if not value:
        return None

    normalized = " ".join(value.replace(",", " ").split())
    for date_format in SOURCE_DATE_FORMATS:
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            pass

    return None


def format_trade_email(trade):
    headline = build_email_headline(trade)
    details = "\n".join(f"{key}: {value}" for key, value in trade.items())

    return (
        f"{headline}\n\n"
        f"{details}\n\n"
        f"Source: {TRADE_URL}\n"
        "This alert is informational only and is not financial advice."
    )


def build_email_subject(trade):
    trade_type = trade.get("Type", "Trade").title()
    issuer = trade.get("Trade Issuer", "Unknown issuer")
    politician = trade.get("Politician", "Unknown politician")

    return f"{EMAIL_SUBJECT}: {trade_type} - {issuer} by {politician}"


def build_email_headline(trade):
    trade_type = trade.get("Type", "trade").lower()
    issuer = trade.get("Trade Issuer", "an issuer")
    politician = trade.get("Politician", "A politician")

    return f"{politician} reported a {trade_type} of {issuer}"


def build_email_html(trade):
    headline = escape(build_email_headline(trade))
    trade_type = escape(trade.get("Type", "Trade").title())
    issuer = escape(trade.get("Trade Issuer", "Unknown issuer"))
    politician = escape(trade.get("Politician", "Unknown politician"))
    size = escape(trade.get("Size", "Unavailable"))
    published = escape(trade.get("Published", "Unavailable"))
    source_url = escape(TRADE_URL)

    rows = "\n".join(
        f"""
        <tr>
          <td style="padding: 11px 0; color: #8A8F98; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.08);">{escape(key)}</td>
          <td style="padding: 11px 0; color: #ffffff; font-size: 14px; font-weight: 700; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.08);">{escape(value)}</td>
        </tr>
        """
        for key, value in trade.items()
    )

    return f"""\
<!doctype html>
<html>
  <body style="margin: 0; padding: 0; background: #0b0d10; font-family: Arial, sans-serif; color: #ffffff;">
    <div style="display: none; max-height: 0; overflow: hidden;">
      {headline}
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background: #0b0d10; padding: 28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 660px; background: #111418; border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; overflow: hidden;">
            <tr>
              <td style="background: #111418; color: #ffffff; padding: 26px 26px 18px; border-bottom: 1px solid rgba(255,255,255,0.08);">
                <div style="color: #53D7C2; font-size: 12px; font-weight: 700; text-transform: uppercase;">Public Disclosure Alert</div>
                <h1 style="margin: 10px 0 0; font-size: 28px; line-height: 1.18;">{headline}</h1>
              </td>
            </tr>
            <tr>
              <td style="padding: 24px 26px 28px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 22px;">
                  <tr>
                    <td style="padding: 16px; background: #151A20; border: 1px solid rgba(255,255,255,0.08); border-radius: 14px;">
                      <div style="color: #8A8F98; font-size: 12px; font-weight: 700; text-transform: uppercase;">Politician</div>
                      <div style="margin-top: 7px; color: #ffffff; font-size: 18px; font-weight: 700;">{politician}</div>
                    </td>
                  </tr>
                  <tr>
                   <td style="height: 10px;"></td>
                  </tr>
                  <tr>
                    <td style="padding: 16px; background: #151A20; border: 1px solid rgba(255,255,255,0.08); border-radius: 14px;">
                      <div style="color: #8A8F98; font-size: 12px; font-weight: 700; text-transform: uppercase;">Trade</div>
                      <div style="margin-top: 7px; color: #53D7C2; font-size: 18px; font-weight: 700;">{trade_type} - {issuer}</div>
                      <div style="margin-top: 5px; color: #8A8F98; font-size: 14px;">Size: {size}</div>
                    </td>
                  </tr>
                </table>

                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse: collapse;">
                  {rows}
                </table>

                <p style="margin: 22px 0 0; color: #8A8F98; font-size: 13px;">
                  Published: {published}
                </p>
                <p style="margin: 16px 0 0;">
                  <a href="{source_url}" style="display: inline-block; background: #53D7C2; color: #06100E; padding: 12px 17px; border-radius: 12px; text-decoration: none; font-weight: 700;">View source</a>
                </p>
                <p style="margin: 18px 0 0; color: #8A8F98; font-size: 12px; line-height: 1.5;">
                  This alert is informational only and is not financial advice.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def validate_email_config():
    missing = [
        name
        for name, value in {
            "EMAIL_SENDER": EMAIL_SENDER,
            "EMAIL_PASSWORD": EMAIL_PASSWORD,
            "EMAIL_RECEIVER": EMAIL_RECEIVER,
        }.items()
        if not value
    ]

    if missing:
        raise EmailConfigError(
            "Missing email configuration: " + ", ".join(missing)
        )


def send_email(trade):
    validate_email_config()

    message = EmailMessage()
    message["From"] = EMAIL_SENDER
    message["To"] = EMAIL_RECEIVER
    message["Subject"] = build_email_subject(trade)
    message.set_content(format_trade_email(trade))
    message.add_alternative(build_email_html(trade), subtype="html")

    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailSendError(
            "Gmail rejected the sender login. Use a fresh Gmail app password "
            "and make sure 2-Step Verification is enabled on the sender account."
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise EmailSendError(
            "Gmail refused the receiver address. Check EMAIL_RECEIVER in .env."
        ) from exc
    except smtplib.SMTPException as exc:
        raise EmailSendError(f"Gmail SMTP error: {exc}") from exc
    except OSError as exc:
        raise EmailSendError(
            f"Could not connect to Gmail SMTP from this network: {exc}"
        ) from exc


def monitor_trades():
    last_fetched_data = None

    while True:
        latest_data = get_latest_trade()

        if latest_data != last_fetched_data:
            send_email(latest_data)
            last_fetched_data = latest_data

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    monitor_trades()
