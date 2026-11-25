#!/bin/bash
set -e

# Nastaví 2x denně samostatné 1-part Reddit Story Shorts (US prime-time, mimo GTA sloty):
# - 20:00 CZ = 14:00 EST / 11:00 PST
# - 01:00 CZ = 19:00 EST / 16:00 PST

BOT_DIR="/root/minecraft_stories_bot"
PY_BIN="/root/gta6_shorts_bot/venv/bin/python3"
LOG_FILE="$BOT_DIR/cron.log"

JOB_1="45 19 * * * $PY_BIN $BOT_DIR/story_bot.py --parts 1 --schedule 20:00 >> $LOG_FILE 2>&1"
JOB_2="45 0 * * * $PY_BIN $BOT_DIR/story_bot.py --parts 1 --schedule 01:00 >> $LOG_FILE 2>&1"

(crontab -l 2>/dev/null | grep -v "story_bot.py" || true; echo "$JOB_1"; echo "$JOB_2") | crontab -

echo "✅ Cron pro Reddit Stories nastaven (2x denně, 1-part <55s, US prime-time):"
crontab -l | grep "story_bot.py"
