import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Tes tidak boleh pernah mengirim ke Telegram / Sheets sungguhan.
for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GSHEET_WEBHOOK_URL", "GOOGLE_SERVICE_ACCOUNT_JSON",
          "GSHEET_SPREADSHEET_ID", "RMF_AGENT_KEY"):
    os.environ.pop(k, None)


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    from rmf import store
    monkeypatch.setattr(store, "STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


@pytest.fixture
def cfg():
    """Config repo, tapi universe 'rolling' supaya koin sintetis (C00, S01, ...) ikut.
    Mode static (daftar riset) dites terpisah di test_momentum.py."""
    import dataclasses

    from rmf import config
    c = config.load()
    return dataclasses.replace(c, universe=dataclasses.replace(c.universe, mode="rolling"), forward_start="")
