#!/bin/bash
set -e

# Nastaví 2x denně automatické generování a publikaci GTA 6 Shorts
# optimalizované pro americké publikum (časy jsou v Europe/Prague):
# - 19:00 CZ = 13:00 EST / 10:00 PST (polední špička východního pobřeží)
# - 00:30 CZ = 18:30 EST / 15:30 PST (večerní herní prime-time v USA)
#
# Cron spouští render o 15 minut dříve (18:45 a 00:15) a předá --schedule,
# aby YouTube stihl video zpracovat před přesným časem zveřejnění.

BOT_DIR="/root/gta6_shorts_bot"
PY_BIN="$BOT_DIR/venv/bin/python3"
LOG_FILE="$BOT_DIR/cron.log"

JOB_1="45 18 * * * $PY_BIN $BOT_DIR/auto_bot.py --mode auto --schedule 19:00 >> $LOG_FILE 2>&1"
JOB_2="15 0 * * * $PY_BIN $BOT_DIR/auto_bot.py --mode auto --schedule 00:30 >> $LOG_FILE 2>&1"

# Odstraní případné staré záznamy auto_bot.py a zapíše nové 2 sloty
(crontab -l 2>/dev/null | grep -v "auto_bot.py" || true; echo "$JOB_1"; echo "$JOB_2") | crontab -

echo "✅ Cron nastaven pro 2 Shorts denně (US prime-time):"
crontab -l | grep "auto_bot.py"
