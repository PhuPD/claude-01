import os
import re
import requests
import pytz
from datetime import datetime
from playwright.sync_api import sync_playwright

URL = "https://thoitiet.vn/ha-noi/ha-dong/theo-gio"
TZ = "Asia/Ho_Chi_Minh"


def fetch_rows():
    """Dùng Playwright để lấy dữ liệu thời tiết theo giờ từ thoitiet.vn."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)

        # Lấy toàn bộ text của trang sau khi JS render xong
        content = page.inner_text("body")
        browser.close()

    return parse_rows(content)


def parse_rows(text):
    rows = []
    # Mỗi block giờ trên thoitiet.vn có dạng: "HH:MM\n<mô tả>\n<nhiệt độ>°C"
    pattern = re.compile(
        r"(\d{1,2}:\d{2})\s*\n\s*([^\n]{3,40}?)\s*\n\s*(\d{1,2}(?:\.\d)?)\s*°?C?(?:\s*/[^\n]*)?\s*\n",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        hour = m.group(1)
        cond = m.group(2).strip()
        temp = m.group(3)
        if cond and not cond.isdigit():
            rows.append((hour, cond, f"{temp}°C"))

    # Fallback: tìm pattern đơn giản hơn nếu không match
    if not rows:
        pattern2 = re.compile(r"(\d{2}:\d{2}).*?([A-ZĐÂÊÔƠƯĂÁÀẢÃẠ][^\n]{2,30})\s*\n\s*(\d{2}(?:\.\d)?)", re.MULTILINE)
        for m in pattern2.finditer(text):
            rows.append((m.group(1), m.group(2).strip(), f"{m.group(3)}°C"))

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
    print(f"Đang lấy dữ liệu từ {URL} ...")
    rows = fetch_rows()

    if not rows:
        print("Không parse được dữ liệu. In raw text để debug:")
        raise SystemExit(1)

    summary = build_summary(rows)
    print(f"\n{summary}\n")
    for hour, cond, temp in rows:
        print(f"  {hour}  {cond:<25}  {temp}")

    write_github_summary(rows, summary)
    send_telegram(summary)


if __name__ == "__main__":
    main()
