#!/usr/bin/env bash
S=C:/Users/U005017/.claude/skills/auto-review
LOGS=/c/Users/U005017/.claude/auto-review/logs
export PATH="/c/Users/U005017/.local/bin:$PATH"
mkdir -p "$LOGS"
find "$LOGS" -name '*.jsonl' -mtime +14 -delete
cd /c/git/OutSystems.ModelExtensions || exit 1
claude -p "Read $S/SKILL.md and follow it. Args: $*" --model opus --settings "$S/settings.json" --permission-mode bypassPermissions --output-format stream-json --verbose 2>&1 | tee "$LOGS/$(date +%Y%m%d-%H%M).jsonl"
