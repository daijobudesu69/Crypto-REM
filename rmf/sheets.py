"""Cermin log ke Google Sheets. Opsional; API-nya menyusul.

Dua cara, yang pertama terkonfigurasi yang dipakai:
  GOOGLE_SERVICE_ACCOUNT_JSON + GSHEET_SPREADSHEET_ID
      service account memanggil Sheets API langsung (spreadsheet dibagikan ke
      client_email service account dengan akses Editor).
  GSHEET_WEBHOOK_URL
      Web app Apps Script (docs/apps_script.gs). Lebih sederhana, tanpa kunci.

Tidak terkonfigurasi = tidak melakukan apa-apa. Tidak pernah raise, dan tidak
pernah mencetak isi secret: exception dilaporkan dengan TIPE saja, karena pesan
exception library bisa memuat URL/kunci dan log workflow repo publik bisa dibaca
siapa saja.
"""
from __future__ import annotations

import json
import os

import requests

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
API = "https://sheets.googleapis.com/v4/spreadsheets"

_session = None
_headers: dict = {}
_disabled = False


def mode() -> str | None:
    if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip() and os.environ.get("GSHEET_SPREADSHEET_ID", "").strip():
        return "service_account"
    if os.environ.get("GSHEET_WEBHOOK_URL", "").strip():
        return "webhook"
    return None


def client_email() -> str:
    try:
        return json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]).get("client_email", "")
    except Exception:  # noqa: BLE001
        return ""


def _sa_session():
    global _session
    if _session is None:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        _session = AuthorizedSession(service_account.Credentials.from_service_account_info(info, scopes=SCOPES))
    return _session


def _sa_header(s, sid: str, tab: str, want: list) -> list:
    """Header tab itu sendiri; kolom baru ditambah di kanan, kolom lama tidak digeser."""
    if tab in _headers:
        return _headers[tab]
    meta = s.get(f"{API}/{sid}?fields=sheets.properties.title", timeout=30)
    meta.raise_for_status()
    titles = [x["properties"]["title"] for x in meta.json().get("sheets", [])]
    if tab not in titles:
        s.post(f"{API}/{sid}:batchUpdate", timeout=30,
               json={"requests": [{"addSheet": {"properties": {"title": tab}}}]}).raise_for_status()
    first = s.get(f"{API}/{sid}/values/{tab}!1:1", timeout=30)
    first.raise_for_status()
    have = [str(c) for c in ((first.json().get("values") or [[]])[0])]
    while have and not have[-1].strip():
        have.pop()
    head = list(want) if not have else have + [c for c in want if c not in have]
    if head != have:
        s.put(f"{API}/{sid}/values/{tab}!A1?valueInputOption=RAW", timeout=30,
              json={"values": [head]}).raise_for_status()
    _headers[tab] = head
    return head


def append(tab: str, cols: list, row: dict) -> bool:
    global _disabled
    m = mode()
    if not m or _disabled:
        return False
    try:
        if m == "service_account":
            s = _sa_session()
            sid = os.environ["GSHEET_SPREADSHEET_ID"].strip()
            head = _sa_header(s, sid, tab, cols)
            vals = [["" if row.get(k) is None else row.get(k, "") for k in head]]
            r = s.post(f"{API}/{sid}/values/{tab}!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
                       json={"values": vals}, timeout=30)
        else:
            r = requests.post(os.environ["GSHEET_WEBHOOK_URL"].strip(),
                              json={"kind": tab, "row": {k: row.get(k, "") for k in cols}}, timeout=30)
        if r.status_code >= 400:
            print(f"[sheets] HTTP {r.status_code} saat menulis '{tab}'")
            if r.status_code in (403, 404) and m == "service_account":
                print(f"[sheets] bagikan spreadsheet ke {client_email()} (akses Editor)")
                _disabled = True          # jangan ulangi ratusan kali di run yang sama
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[sheets] gagal: {type(e).__name__}")
        return False


def backfill(tab: str, cols: list, rows: list) -> str:
    """Isi tab yang masih KOSONG (hanya header / belum ada) dengan semua baris CSV.

    Tab yang sudah berisi data tidak disentuh, supaya tidak ada baris ganda.
    Hanya untuk service account (webhook tidak bisa membaca isi tab).
    """
    if mode() != "service_account":
        return "dilewati (bukan service account)"
    try:
        s = _sa_session()
        sid = os.environ["GSHEET_SPREADSHEET_ID"].strip()
        head = _sa_header(s, sid, tab, cols)
        got = s.get(f"{API}/{sid}/values/{tab}!A:A", timeout=30)
        got.raise_for_status()
        n = len(got.json().get("values") or [])
        if n > 1:
            return f"sudah berisi {n - 1} baris, tidak diisi ulang"
        if not rows:
            return "header dibuat, belum ada baris"
        vals = [["" if r.get(k) is None else r.get(k, "") for k in head] for r in rows]
        r = s.post(f"{API}/{sid}/values/{tab}!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
                   json={"values": vals}, timeout=60)
        if r.status_code >= 400:
            return f"HTTP {r.status_code}" + (f" — bagikan spreadsheet ke {client_email()}" if r.status_code in (403, 404) else "")
        return f"{len(rows)} baris diisi"
    except Exception as e:  # noqa: BLE001
        return f"gagal: {type(e).__name__}"
