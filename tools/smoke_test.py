"""Smoke test semua sambungan, dijalankan manual lewat workflow smoke.yml.

  1. Telegram : pesan TEST + kirim ulang ringkasan momentum terakhir dari state/
  2. Sheets   : tab yang masih kosong diisi semua baris CSV yang sudah ada
  3. HYPE key : HANYA BACA — format kunci, alamat agent, akun utama, nama &
                masa berlaku API wallet, daftar subaccount. Tidak ada order.
  4. Data     : HYPE /info dan Binance spot terjangkau

Kunci privat tidak pernah dicetak. Log repo publik bisa dibaca siapa saja, jadi
log hanya berisi status; detail akun (alamat, subaccount) dikirim ke Telegram.
Exit 1 kalau ada pemeriksaan yang gagal.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmf import binance, config, control, hype, jobs, notify, sheets, store  # noqa: E402

BANNER = ("\U0001F9EA <b>TEST — bukan sinyal aktif</b>\n"
          "<i>Dikirim manual oleh smoke test untuk mengecek sambungan dan tampilan.</i>\n\n")


def check_data(cfg) -> list:
    out = []
    try:
        n = len(hype.InfoClient(cfg.hype.info_url).meta())
        out.append(("HYPE /info", True, f"{n} perp"))
    except Exception as e:  # noqa: BLE001
        out.append(("HYPE /info", False, type(e).__name__))
    try:
        k = binance.KlineClient("binance_spot").klines("BTCUSDT", "4h", 5)
        out.append(("Binance spot", len(k) > 0, f"{len(k)} candle"))
    except Exception as e:  # noqa: BLE001
        out.append(("Binance spot", False, type(e).__name__))
    return out


def check_sheets() -> list:
    m = sheets.mode()
    if not m:
        return [("Google Sheets", False, "secret belum diisi")]
    res = []
    for log in ("equity", "orders", "flush_trades", "flush_signals"):
        rows = store.read(log)
        if log == "flush_signals":
            rows = [r for r in rows if r.get("event") in ("1", "True", "true")]
        msg = sheets.backfill(log, store.COLUMNS[log], rows)
        res.append((f"Sheets tab {log}", not msg.startswith(("gagal", "HTTP")), msg))
    return res


def check_hype_key(cfg, now) -> tuple[list, str]:
    """Return (hasil, detail untuk Telegram)."""
    key = os.environ.get("RMF_AGENT_KEY", "").strip()
    src = os.environ.get("RMF_AGENT_KEY_SOURCE", "")
    if not key:
        return [("HYPE API wallet", False, "secret HYPE_RMF_AGENT_KEY_66_CHAR kosong")], ""
    if not (key.startswith("0x") and len(key) == 66):
        return [("HYPE API wallet", False, f"panjang {len(key)}, harus 66 (0x + 64 hex) — "
                                            "mungkin yang diisi alamat, bukan private key")], ""
    try:
        import eth_account
        agent = eth_account.Account.from_key(key).address
    except Exception as e:  # noqa: BLE001
        return [("HYPE API wallet", False, f"kunci tidak valid ({type(e).__name__})")], ""
    info = hype.InfoClient(cfg.hype.info_url)
    res = [("HYPE API wallet", True, f"kunci valid (secret {src})")]
    lines = [f"  sumber secret: <code>{notify.esc(src)}</code>", f"  alamat agent: <code>{agent}</code>"]
    try:
        role = info.post({"type": "userRole", "user": agent}, weight=60)
    except Exception as e:  # noqa: BLE001
        res.append(("HYPE agent terdaftar", False, type(e).__name__))
        return res, "\n".join(lines)
    master = ((role or {}).get("data") or {}).get("user") if (role or {}).get("role") == "agent" else None
    if not master:
        res.append(("HYPE agent terdaftar", False, f"role = {(role or {}).get('role')}, bukan agent"))
        return res, "\n".join(lines)
    lines.append(f"  akun utama: <code>{master}</code>")
    try:
        agents = info.post({"type": "extraAgents", "user": master})
        me = next((a for a in agents if str(a.get("address", "")).lower() == agent.lower()), None)
        if me:
            vu = me.get("validUntil")
            until = dt.datetime.fromtimestamp(int(vu) / 1000, dt.timezone.utc).date() if vu else None
            days = (until - now.date()).days if until else None
            lines.append(f"  nama API wallet: <b>{notify.esc(me.get('name', '-'))}</b>")
            lines.append(f"  berlaku sampai: {until} ({days} hari lagi)" if until else "  berlaku sampai: -")
            res.append(("HYPE agent terdaftar", days is None or days >= 0, f"berlaku {days} hari lagi"))
        else:
            res.append(("HYPE agent terdaftar", False, "tidak ada di daftar API wallet akun utama"))
        subs = info.post({"type": "subAccounts", "user": master}) or []
        if subs:
            lines.append("  subaccount:")
            for s in subs:
                lines.append(f"    • {notify.esc(s.get('name', '-'))}: <code>{s.get('subAccountUser')}</code>")
        else:
            lines.append("  subaccount: belum ada — buat subaccount khusus RMF")
    except Exception as e:  # noqa: BLE001
        res.append(("HYPE akun utama", False, type(e).__name__))
    ex = cfg.execution
    if ex.agent_address and ex.agent_address.lower() != agent.lower():
        res.append(("config agent_address", False, "tidak sama dengan alamat dari kunci"))
    return res, "\n".join(lines)


def main() -> int:
    cfg = config.load()
    now = dt.datetime.now(dt.timezone.utc)
    results = check_data(cfg)
    results += check_sheets()
    hres, hdetail = check_hype_key(cfg, now)
    results += hres

    tele_ok = notify.configured()
    results.append(("Telegram secret", tele_ok, "terisi" if tele_ok else "belum diisi"))
    for name, ok, msg in results:
        print(f"[smoke] {'OK  ' if ok else 'GAGAL'} {name}: {msg}")

    t = now.strftime("%Y-%m-%d %H:%M")
    body = "\n".join(f"  {'✅' if ok else '❌'} {notify.esc(n)}: {notify.esc(m)}" for n, ok, m in results)
    report = (f"{BANNER}\U0001F9EA <b>RMF — smoke test</b>\n<code>{t} UTC</code>\n\n{body}"
              + (f"\n\n<b>Akun HYPE (hanya baca)</b>\n{hdetail}" if hdetail else "")
              + "\n\n<i>Tidak ada order yang dikirim.</i>")
    sent = notify.send_now(report)
    ctx = jobs.Ctx(cfg=cfg, info=None, klines=None, ctrl=control.read(), outbox=notify.Outbox(now), now=now)
    daily = jobs.daily_message_from_state(ctx)
    if daily:
        sent &= notify.send_now(BANNER + daily)
    print(f"[smoke] telegram terkirim: {sent}; ringkasan harian: {'ada' if daily else 'belum ada'}")
    return 0 if all(ok for _, ok, _ in results) and sent else 1


if __name__ == "__main__":
    sys.exit(main())
