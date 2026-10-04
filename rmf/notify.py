"""Telegram dengan outbox. API-nya menyusul; tanpa token, pesan dicetak ke log.

Aturan:
  * Run tidak pernah gagal karena Telegram. CSV di state/ adalah catatan resmi.
  * Pesan yang gagal terkirim disimpan di state/outbox.json dan dicoba ulang di
    siklus berikutnya (maks 48 jam), supaya gangguan Telegram tidak menelan
    pesan penting seperti alarm DD.
  * Error dilaporkan dengan tipe saja: exception requests memuat URL, dan URL
    Telegram memuat token bot.
"""
from __future__ import annotations

import datetime as dt
import html
import os

import requests

from . import store

API = "https://api.telegram.org/bot{token}/sendMessage"
OUTBOX = "outbox.json"
MAX_AGE_H = 48


def esc(x) -> str:
    return html.escape(str(x), quote=False)


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() and os.environ.get("TELEGRAM_CHAT_ID", "").strip())


def send_now(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat):
        print("[notify] Telegram belum dikonfigurasi — pesan tidak dikirim:\n" + text + "\n")
        return True                       # tidak ada yang perlu dicoba ulang
    try:
        r = requests.post(API.format(token=token), timeout=25,
                          json={"chat_id": chat, "text": text[:4000], "parse_mode": "HTML",
                                "disable_web_page_preview": True})
        if r.status_code >= 400:
            print(f"[notify] telegram HTTP {r.status_code}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[notify] telegram gagal: {type(e).__name__}")
        return False


class Outbox:
    def __init__(self, now: dt.datetime | None = None):
        self.now = now or dt.datetime.now(dt.timezone.utc)
        self.items = store.load_json(OUTBOX, []) or []

    def add(self, text: str) -> None:
        self.items.append({"time": self.now.isoformat(), "text": text})

    def flush(self) -> int:
        """Kirim semua; return jumlah yang masih tertahan."""
        keep = []
        for it in self.items:
            age = (self.now - dt.datetime.fromisoformat(it["time"])).total_seconds() / 3600
            if age > MAX_AGE_H:
                print(f"[notify] pesan dari {it['time']} dibuang (> {MAX_AGE_H} jam)")
                continue
            if keep or not send_now(it["text"]):
                keep.append(it)           # urutan dijaga: berhenti di kegagalan pertama
        self.items = keep
        store.save_json(OUTBOX, keep)
        return len(keep)


def wib(t) -> str:
    t = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00")) if not isinstance(t, dt.datetime) else t
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(dt.timezone(dt.timedelta(hours=7))).strftime("%d-%m-%Y %H:%M WIB")


def usd(x) -> str:
    return "-" if x is None else f"{float(x):,.2f}"


def pct(x, n=1) -> str:
    return "-" if x is None else f"{float(x) * 100:+.{n}f}%"
