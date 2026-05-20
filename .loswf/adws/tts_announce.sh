#!/usr/bin/env bash
# tts_announce.sh — silent-by-default native TTS announcement helper.
#
# Usage: tts_announce.sh <agent> <message>
#
# Behavior:
#   - Silent by default. Only emits audio when LOSWF_SPEAK=1.
#   - Hard no-op (exit 0) when `edge-tts` or `afplay` binaries are missing
#     (macOS-only audibly; Linux/CI no-op by design).
#   - Never aborts its caller (uses `set -u` but NOT `set -e`; every
#     external command has `|| exit 0`).
#   - Maps agent name to an edge-tts voice. Accepts namespaced
#     (`loswf:builder`), prefixed (`loswf-builder`), and bare (`builder`)
#     forms so both `_lib.sh` (bare) and transcript-derived (namespaced)
#     callers work.
#
# Note: `~/.claude/tts/speak-dispatch.sh` may double-announce if both are
# enabled — this helper is intentionally independent of that dispatcher.

set -u

agent="${1:-}"
message="${2:-}"

[ -n "$agent" ] && [ -n "$message" ] || exit 0

[ "${LOSWF_SPEAK:-}" = "1" ] || exit 0

case "$agent" in
  loswf:planner|loswf-planner|planner)                        VOICE=en-GB-RyanNeural ;;
  loswf:builder|loswf-builder|builder)                        VOICE=en-US-GuyNeural ;;
  loswf:reviewer|loswf-reviewer|reviewer)                     VOICE=en-AU-WilliamMultilingualNeural ;;
  loswf:plan-reviewer|loswf-plan-reviewer|plan-reviewer)      VOICE=en-GB-LibbyNeural ;;
  loswf:decomposer|loswf-decomposer|decomposer)               VOICE=en-US-BrianNeural ;;
  loswf:architect|loswf-architect|architect)                  VOICE=en-US-ChristopherNeural ;;
  loswf:intake|loswf-intake|intake)                           VOICE=en-US-EmmaNeural ;;
  loswf:investigator|loswf-investigator|investigator)         VOICE=en-US-AnaNeural ;;
  loswf:curator|loswf-curator|curator)                        VOICE=en-US-JennyNeural ;;
  loswf:harvester|loswf-harvester|harvester)                  VOICE=en-US-MichelleNeural ;;
  loswf:documenter|loswf-documenter|documenter)               VOICE=en-AU-NatashaNeural ;;
  loswf:setup|loswf-setup|setup)                              VOICE=en-GB-SoniaNeural ;;
  *)                                                          VOICE=en-US-AriaNeural ;;
esac

command -v edge-tts >/dev/null 2>&1 || exit 0
command -v afplay >/dev/null 2>&1 || exit 0

TMP=$(mktemp -t loswf-tts.XXXXXX).mp3
trap 'rm -f "$TMP"' EXIT

edge-tts --voice "$VOICE" --text "$message" --write-media "$TMP" >/dev/null 2>&1 || exit 0
afplay "$TMP" >/dev/null 2>&1 || exit 0

exit 0
