import os
import re
import requests
import pytz
from datetime import datetime

URL = "https://thoitiet.vn/ha-noi/ha-dong/theo-gio"
TZ = "Asia/Ho_Chi_Minh"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9",
}


def fetch_rows():
    """Fetch hourly rows from thoitiet.vn. Returns list of (hour, condition, temp)."""
    from bs4 import BeautifulSoup

    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    rows = []

    # thoitiet.vn renders hourly blocks — find all time+condition+temp groups
    # Try common selectors; adjust if site structure changes
    for item in soup.select(".hourly-item, .hour-item, [class*='hourly'], [class*='hour-item']"):
        time_el = item.select_one("[class*='time'], [class*='hour']")
        cond_el = item.select_one("[class*='desc'], [class*='condition'], [class*='weather'], img[alt]")
        temp_el = item.select_one("[class*='temp'], [class*='temperature']")

        hour = time_el.get_text(strip=True) if time_el else None
        cond = (
            cond_el.get("alt", "").strip() or cond_el.get_text(strip=True)
            if cond_el else None
        )
        temp = temp_el.get_text(strip=True).replace("°", "").replace("C", "").strip() if temp_el else None

        if hour and cond and temp:
            rows.append((hour, cond, temp))

    # Fallback: scan all text for HH:MM pattern near temperature
    if not rows:
        rows = _fallback_parse(soup)

    return rows


def _fallback_parse(soup):
    """Last-resort: extract time/condition/temp from raw text blocks."""
    rows = []
    text = soup.get_text(separator="\n")
    # Look for lines like "15:00\nNhiều mây\n32°C"
    pattern = re.compile(
        r"(\d{1,2}:\d{2})\s*\n\s*([^\n]{3,40})\s*\n\s*(\d{1,2}(?:\.\d)?)\s*°?C?",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        rows.append((m.group(1), m.group(2).strip(), m.group(3) + "°C"))
    return rows


def build_summary(rows):
    tz = pytz.timezone(TZ)
    date_str = datetime.now(tz).strftime("%d/%m")

    temps = []
    for _, _, t in rows:
        try:
            temps.append(float(re.sub(r"[^\d.]", "", t)))
        except ValueError:
            pass

    rain = [(h, c) for h, c, _ in rows if any(w in c for w in ("Mưa", "mưa", "Dông", "dông"))]
    heavy = [(h, c) for h, c in rain if any(w in c for w in ("to", "nặng", "rào", "Dông", "dông"))]

    temp_range = f"{round(min(temps))}–{round(max(temps))}°C" if temps else "N/A"

    if not rain:
        weather_msg = "Không mưa ☀️"
    else:
        weather_msg = f"Mưa {rain[0][0]}–{rain[-1][0]} 🌧"
        if heavy:
            weather_msg += f", mưa to nhất {heavy[0][0]}"

    return f"Hà Đông {date_str}: {temp_range} | {weather_msg}"


def write_github_summary(rows, summary):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    tz = pytz.timezone(TZ)
    now_str = datetime.now(tz).strftime("%H:%M %d/%m/%Y")
    lines = [
        f"# ☁️ Thời tiết Hà Đông — {now_str}\n",
        f"Nguồn: [{URL}]({URL})\n",
        "| Giờ | Thời tiết | Nhiệt độ |",
        "|---|---|---|",
    ]
    for hour, cond, temp in rows:
        lines.append(f"| {hour} | {cond} | {temp} |")
    lines.append(f"\n**Tóm tắt:** {summary}")
    with open(path, "w") as f:
        f.write("\n".join(lines))


def send_telegram(summary):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram chưa cấu hình, bỏ qua.")
        return
    text = (
        f"☁️ *Thời tiết Hà Đông*\n\n{summary}"
        f"\n\n[Xem chi tiết theo giờ]({URL})"
    )
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=30,
    )
    r.raise_for_status()
    print("Đã gửi Telegram.")


def main():
    rows = fetch_rows()
    if not rows:
        print("Không lấy được dữ liệu từ thoitiet.vn")
        raise SystemExit(1)

    summary = build_summary(rows)
    print(summary)
    for hour, cond, temp in rows:
        print(f"  {hour}  {cond:<25}  {temp}")

    write_github_summary(rows, summary)
    send_telegram(summary)


if __name__ == "__main__":
    main()
