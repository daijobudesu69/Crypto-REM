#!/usr/bin/env bash
# Samakan working tree dengan origin SEBELUM siklus membaca state.
#
# Job watcher checkout sekali lalu hidup ~5,5 jam. Saat pergantian job, job baru
# bisa checkout sebelum push terakhir job lama mendarat, lalu memproses ulang
# hari/bar yang sudah selesai (dan mengirim pesan dua kali). Pola dari Crypto-MEX.
#
# Tidak pernah membuang pekerjaan: dilewati kalau ada perubahan state/ yang belum
# di-commit atau commit lokal yang belum ter-push (save_state.sh yang mengurus).
set -uo pipefail

BRANCH="${GITHUB_REF_NAME:-main}"

if ! git fetch -q origin "${BRANCH}" 2>/dev/null; then
  echo "[refresh] fetch gagal; lanjut dengan state lokal"
  exit 0
fi

# control/bot.yaml harus terbaca tiap siklus, JUGA saat reset di bawah dilewati.
if git show "origin/${BRANCH}:control/bot.yaml" > .rmf_control_origin.yaml.tmp 2>/dev/null; then
  mv -f .rmf_control_origin.yaml.tmp .rmf_control_origin.yaml
else
  rm -f .rmf_control_origin.yaml.tmp .rmf_control_origin.yaml
fi

if [ -n "$(git status --porcelain state/ 2>/dev/null)" ]; then
  echo "[refresh] ada perubahan state/ belum ter-commit; tidak disentuh"
  exit 0
fi
if [ -n "$(git rev-list "origin/${BRANCH}..HEAD" 2>/dev/null)" ]; then
  echo "[refresh] ada commit lokal belum ter-push; tidak disentuh"
  exit 0
fi
local_sha="$(git rev-parse HEAD)"
origin_sha="$(git rev-parse "origin/${BRANCH}")"
if [ "$local_sha" = "$origin_sha" ]; then
  echo "[refresh] sudah sinkron"
  exit 0
fi
git reset -q --hard "origin/${BRANCH}"
echo "[refresh] disinkronkan ${local_sha:0:8} -> ${origin_sha:0:8}"
