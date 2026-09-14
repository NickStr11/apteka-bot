#!/usr/bin/env bash
# Deploy only the reviewed callback patch over the existing production checkout.
set -euo pipefail
cd /opt/apteka-bot
base=7bd4e9b
target=f6247f5
source_file=src/bot/telegram_bot.py
test_file=tests/test_order_resilience.py
new_test=tests/test_telegram_dispatch.py
git cat-file -e "$target^{commit}"
patch_file=$(mktemp /tmp/apteka-callback-patch.XXXXXX)
git diff "$base" "$target" -- "$source_file" "$test_file" "$new_test" > "$patch_file"
# Preserve the existing server-only escape_markdown import.
python3 - "$patch_file" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
patch = p.read_text()
live = Path('src/bot/telegram_bot.py').read_text()
anchor = 'from telegram.helpers import escape_markdown\n'
if anchor in live:
    old = '-from telegram.error import TimedOut\n'
    assert patch.count(old) == 1, 'Unexpected patch import context'
    patch = patch.replace(old, ' ' + anchor + old, 1)
p.write_text(patch)
PY
if git apply --recount --reverse --check "$patch_file" 2>/dev/null; then
    echo 'ALREADY_INSTALLED: callback fix f6247f5'
    systemctl is-active apteka-bot
    exit 0
fi
git apply --recount --check "$patch_file"
backup=$(mktemp -d "$PWD/runtime/backups/callback-fix-$(date -u +%Y%m%d-%H%M%S).XXXXXX")
test -f "$source_file"
test -f "$test_file"
test ! -e "$new_test"
tar -czf "$backup/before.tgz" "$source_file" "$test_file"
cp "$patch_file" "$backup/applied.patch"
changed=0
restart_attempted=0
rollback() {
    rc=$?
    trap - EXIT
    if (( rc != 0 && changed == 1 )); then
        tar -xzf "$backup/before.tgz" -C /opt/apteka-bot
        if [[ -f "$new_test" ]]; then mv -- "$new_test" "$backup/failed-test_telegram_dispatch.py"; fi
        if (( restart_attempted == 1 )); then systemctl restart apteka-bot || true; fi
        echo "ROLLED_BACK: deployment failed; backup=$backup"
    fi
    exit "$rc"
}
trap rollback EXIT
git apply --recount "$patch_file"
changed=1
.venv/bin/python -m unittest discover -s tests -p test_order_resilience.py
.venv/bin/python -m unittest discover -s tests -p test_telegram_dispatch.py
.venv/bin/python -c 'import sys; sys.path.insert(0,"src"); import bot.telegram_bot; print("IMPORT_OK")'
restart_attempted=1
systemctl restart apteka-bot
sleep 5
systemctl is-active --quiet apteka-bot
echo "DEPLOY_OK: f6247f5; backup=$backup"
systemctl show apteka-bot -p ActiveState -p SubState -p NRestarts
date -u
