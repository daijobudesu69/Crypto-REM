#!/usr/bin/env bash
# Tulis control/bot.yaml lalu push. Dipanggil .github/workflows/control.yml.
# Tiap percobaan mulai dari origin terbaru, jadi tidak pernah konflik dengan
# commit state dari watcher.
#
# Env: MOMENTUM (tetap|off|paper|live|manage|flatten), FLUSH (tetap|off|paper), RESET (true|false)
set -uo pipefail

BRANCH="${GITHUB_REF_NAME:-main}"
git config user.name  "rmf-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

args=(--momentum "${MOMENTUM:-tetap}" --flush "${FLUSH:-tetap}")
if [ "${RESET:-false}" = "true" ]; then args+=(--reset-breaker); fi

for i in 1 2 3 4 5; do
  if ! git fetch -q origin "${BRANCH}"; then sleep $((i * 3)); continue; fi
  git reset -q --hard "origin/${BRANCH}"
  out="$(python tools/set_control.py "${args[@]}")" || { echo "$out"; exit 2; }
  echo "$out"
  git add control/
  if git diff --cached --quiet -- control/; then
    echo "[control] tidak ada perubahan"
    exit 0
  fi
  git commit -q -m "control: ${out#\[control\] } [skip ci]"
  if git push -q origin "HEAD:${BRANCH}"; then
    echo "[control] tersimpan; watcher memakainya di siklus berikutnya (<= ~10 menit)"
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$out" >> "$GITHUB_STEP_SUMMARY"; fi
    exit 0
  fi
  echo "[control] push ditolak, ulang dari origin (percobaan $i)"
  sleep $((i * 3))
done
echo "::error::gagal menyimpan control/bot.yaml"
exit 1
