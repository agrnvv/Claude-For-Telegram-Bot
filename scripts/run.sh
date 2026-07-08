#!/usr/bin/env bash
# Convenience launcher: activates the venv (if present) and starts the bot
# with long polling. Intended to be run under systemd/pm2/screen for uptime.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m claudefortelegram.main
