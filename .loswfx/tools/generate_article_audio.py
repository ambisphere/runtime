#!/usr/bin/env python3
"""Generate spoken-word audio for a devlog article via OpenAI TTS.

Reads a markdown article (frontmatter + body), strips formatting to
plain text, splits into chunks that fit OpenAI's per-call limit, calls
`v1/audio/speech` with the configured voice, and concatenates the
resulting MP3 bytes into a single `audio.mp3` next to the article.
Writes a receipt JSON alongside.

Replaces the browser-native `window.speechSynthesis` fallback that
caps out around ~250 chars in Chrome (the "cuts off before completing
long article" bug). The Hugo template (`layouts/news/single.html`)
already looks for `audio.mp3` as a sibling resource and prefers it
over speech synthesis when present.

Default model is `gpt-4o-mini-tts` (steerable via the `instructions`
param). Default voice is `echo` (neutral, technical, doesn't push
character on the listener). Both overridable on the CLI.

CLI:
  generate_article_audio.py --md <article.md> [--out audio.mp3]
                            [--voice echo|onyx|sage|alloy|...]
                            [--model gpt-4o-mini-tts|tts-1|tts-1-hd]
                            [--instructions "<voice-steer prompt>"]
                            [--max-chars-per-chunk 4000]
                            [--speed 1.0]

Exit codes:
  0 — audio written.
  1 — generation failed (API error after retries) — receipt written.
  2 — operator error (missing key, bad args, file not found).

Receipt schema: loswf-article-audio-receipt-v1.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.openai.com/v1/audio/speech"
RECEIPT_SCHEMA = "loswf-article-audio-receipt-v1"
DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "echo"
DEFAULT_FORMAT = "mp3"
DEFAULT_MAX_CHARS = 4000  # OpenAI per-call limit is 4096; leave headroom
DEFAULT_TIMEOUT_SEC = 180

# Indicative pricing — gpt-4o-mini-tts is billed by output tokens
# (audio), not input chars. The per-1M-char estimate below is a
# conservative back-of-envelope using observed ratios; receipts
# capture exact char count so operators can reconcile against
# the OpenAI invoice.
_COST_PER_1M_CHARS = {
    "gpt-4o-mini-tts": 12.00,
    "tts-1": 15.00,
    "tts-1-hd": 30.00,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


# ---------------------------------------------------------------------------
# Markdown → plain text
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_FENCED_CODE_RE = re.compile(r"```[^\n]*\n.*?\n```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HEADING_RE = re.compile(r"^#+\s+", re.MULTILINE)
_EMPH_RE = re.compile(r"(\*\*|__|_|\*)")
_HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE)
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def markdown_to_plain(text: str) -> str:
    """Strip markdown formatting and frontmatter so the TTS reads
    natural prose. The conversion is lossy by design — code blocks,
    image syntax, and inline emphasis are noise to a listener.

    Tries to preserve sentence boundaries so the chunker can split
    cleanly later."""
    s = _FRONTMATTER_RE.sub("", text)
    # Drop fenced code blocks entirely; their content reads as noise.
    s = _FENCED_CODE_RE.sub(" ", s)
    # Image syntax → drop entirely; visually-anchored alt text rarely
    # reads well aloud and operators are inconsistent about writing it.
    s = _IMAGE_RE.sub("", s)
    # Inline links → keep the visible text only.
    s = _LINK_RE.sub(r"\1", s)
    # Inline code → keep the body without backticks.
    s = _INLINE_CODE_RE.sub(r"\1", s)
    # Headings → drop the leading hashes; keep the title text.
    s = _HEADING_RE.sub("", s)
    # Horizontal rules → drop.
    s = _HR_RE.sub("", s)
    # Emphasis markers → drop.
    s = _EMPH_RE.sub("", s)
    # Collapse triple-or-more blank lines.
    s = _BLANK_LINES_RE.sub("\n\n", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Pronunciation substitution
# ---------------------------------------------------------------------------

# Default phonetic substitutions for brand words the TTS would
# otherwise mispronounce. `loswf` is canonical pronounced "low swiff"
# (two syllables, /loʊ swɪf/), but gpt-4o-mini-tts inferred
# "Lasweff" from the unusual letter sequence. Substituting before
# the TTS call removes the inference entirely — the model just reads
# "low swiff" as two English words.
#
# Order matters: longer patterns first so `loswfx` doesn't get
# substituted as `low swiff` + `x`. The `\b` anchors prevent
# partial-word matches like LOSWF_DEVLOG_PAT (which wouldn't survive
# markdown-strip anyway, but defensive).
#
# Operators can extend or override via .loswf/config.yaml:
#   article_audio:
#     pronunciations:
#       custom_term: "phonetic spelling"
_DEFAULT_PRONUNCIATIONS = [
    # Khaos brand family — "Kh" is silent, the word is canonically
    # pronounced exactly like English "chaos" (/ˈkeɪɒs/). Substituting
    # to the English spelling makes the TTS read it correctly. Longer
    # multi-word brands first so the shorter "Khaos" doesn't match
    # inside them first.
    ("Khaos Machine", "Chaos Machine"),
    ("Khaos Storage", "Chaos Storage"),
    ("Khaos Story",   "Chaos Story"),
    ("Khaos",         "Chaos"),
    # loswf family — pronounced "low swiff" (/loʊ swɪf/). TTS would
    # otherwise infer "Lasweff" from the unusual consonant cluster.
    ("loswfx", "low swiff ex"),
    ("loswf2", "low swiff two"),
    ("loswf",  "low swiff"),
]


def _compile_pronunciation_rules(extra: dict | None) -> list[tuple[re.Pattern, str]]:
    """Build a list of (compiled_pattern, replacement) rules. Order is
    longest-pattern-first so longer brand variants substitute before
    shorter ones. Multi-word literals are compiled with `\\s+` between
    tokens so the rule still fires when markdown wraps a brand name
    across a line break."""
    rules: list[tuple[str, str]] = list(_DEFAULT_PRONUNCIATIONS)
    if extra:
        # Operator overrides: replace defaults that share a key; add
        # new entries. Final ordering is longest-first.
        existing_keys = {k for k, _ in rules}
        for k, v in extra.items():
            if k in existing_keys:
                # Replace the existing rule's replacement.
                rules = [(rk, v if rk == k else rv) for rk, rv in rules]
            else:
                rules.append((k, str(v)))
    rules.sort(key=lambda kv: -len(kv[0]))
    compiled: list[tuple[re.Pattern, str]] = []
    for k, v in rules:
        # Tokenize on whitespace so multi-word brands ("Khaos Machine",
        # "Chaos Story") match across single spaces, multiple spaces,
        # and newline-wrapped paragraphs equally. Each token is
        # re.escape()'d defensively for any future entries that
        # contain regex meta-characters.
        tokens = k.split()
        if len(tokens) == 0:
            continue
        body = r"\s+".join(re.escape(t) for t in tokens)
        pattern = re.compile(rf"\b{body}\b", re.IGNORECASE)
        compiled.append((pattern, v))
    return compiled


def apply_pronunciations(text: str,
                          rules: list[tuple[re.Pattern, str]]) -> tuple[str, dict[str, int]]:
    """Apply pronunciation rules. Returns (transformed_text, counts).
    Counts map the original literal pattern (e.g. "loswfx") to the
    number of substitutions made — surfaced in the receipt so
    operators can verify the brand voice landed."""
    counts: dict[str, int] = {}
    for pattern, replacement in rules:
        new_text, n = pattern.subn(replacement, text)
        if n > 0:
            # Use the replacement string as the receipt key — more
            # legible than the raw regex source (which carries `\b`
            # anchors and `\s+` connectors).
            counts[replacement] = counts.get(replacement, 0) + n
            text = new_text
    return text, counts


def _load_pronunciation_overrides(config_path: Path | None) -> dict | None:
    """Read `article_audio.pronunciations` from .loswf/config.yaml if
    pyyaml is installed and the block exists. Returns None on any
    failure — the default rules ship as a sane baseline regardless."""
    if config_path is None or not config_path.exists():
        return None
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return None
    block = data.get("article_audio") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return None
    pron = block.get("pronunciations")
    if isinstance(pron, dict) and pron:
        return {str(k): str(v) for k, v in pron.items()}
    return None


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text into chunks <= max_chars, preferring paragraph
    boundaries (blank lines), falling back to sentence boundaries
    when a paragraph is too long, falling back to hard splits when a
    sentence is too long (rare in normal prose).

    Returns at least one chunk for non-empty input. Empty input
    returns an empty list."""
    text = text.strip()
    if not text:
        return []
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue
        # Flush whatever we had.
        if current:
            chunks.append(current)
            current = ""
        # If this paragraph alone fits, start a new chunk with it.
        if len(para) <= max_chars:
            current = para
            continue
        # Paragraph too long; split on sentence boundaries.
        sentences = _SENTENCE_BOUNDARY_RE.split(para)
        sub_current = ""
        for sent in sentences:
            sub_candidate = (sub_current + " " + sent) if sub_current else sent
            if len(sub_candidate) <= max_chars:
                sub_current = sub_candidate
            else:
                if sub_current:
                    chunks.append(sub_current)
                if len(sent) <= max_chars:
                    sub_current = sent
                else:
                    # Sentence too long; hard split. Very rare.
                    for i in range(0, len(sent), max_chars):
                        chunks.append(sent[i:i + max_chars])
                    sub_current = ""
        if sub_current:
            current = sub_current
    if current:
        chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# OpenAI TTS call
# ---------------------------------------------------------------------------

def _tts_call(text: str, *, model: str, voice: str, fmt: str,
              speed: float, instructions: str | None,
              api_key: str, timeout: int,
              max_transient_retries: int = 2) -> bytes:
    """Single TTS call with retry on transient failures.

    Mirrors generate_image.py's retry shape:
      - 429: one retry after Retry-After (or 5s) + 1s.
      - 5xx, TimeoutError, socket.timeout, URLError(timeout):
        up to max_transient_retries retries with 10s -> 30s backoff.
      - 4xx (other than 429): no retry; raise SystemExit(1).

    Returns the raw audio bytes (binary, not base64) on success."""
    payload: dict = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": fmt,
    }
    if speed != 1.0:
        payload["speed"] = speed
    if instructions:
        payload["instructions"] = instructions

    backoff_schedule = [10, 30]
    transient_attempts = 0
    rate_limit_attempts = 0
    attempts = 0
    while True:
        attempts += 1
        req = urllib.request.Request(
            API_URL,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload).encode("utf-8"),
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and rate_limit_attempts == 0:
                rate_limit_attempts += 1
                retry_after = e.headers.get("retry-after") if e.headers else None
                try:
                    delay = float(retry_after) if retry_after else 5.0
                except ValueError:
                    delay = 5.0
                print(
                    f"openai tts rate-limited (attempt {attempts}); sleeping {delay + 1:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(max(0.0, delay) + 1.0)
                continue
            if 500 <= e.code < 600 and transient_attempts < max_transient_retries:
                delay = backoff_schedule[transient_attempts]
                transient_attempts += 1
                print(
                    f"openai tts {e.code} (attempt {attempts}); retrying in {delay}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(f"openai tts error {e.code}: {body[:500]}", file=sys.stderr)
            raise SystemExit(1)
        except (TimeoutError, socket.timeout) as e:
            if transient_attempts < max_transient_retries:
                delay = backoff_schedule[transient_attempts]
                transient_attempts += 1
                print(
                    f"openai tts read timed out (attempt {attempts}); retrying in {delay}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(
                f"openai tts persistently timed out after {attempts} attempts: {e}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        except urllib.error.URLError as e:
            inner = e.reason
            is_timeout = isinstance(inner, (TimeoutError, socket.timeout))
            if is_timeout and transient_attempts < max_transient_retries:
                delay = backoff_schedule[transient_attempts]
                transient_attempts += 1
                print(
                    f"openai tts connect timed out (attempt {attempts}); retrying in {delay}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(f"openai tts unreachable: {e}", file=sys.stderr)
            raise SystemExit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="generate_article_audio.py")
    p.add_argument("--md", required=True, type=Path,
                   help="path to the markdown article (frontmatter + body)")
    p.add_argument("--out", type=Path, default=None,
                   help="output mp3 path. Defaults to audio.mp3 next to --md.")
    p.add_argument("--voice", default=DEFAULT_VOICE,
                   help=f"openai voice id. default {DEFAULT_VOICE}.")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"openai tts model. default {DEFAULT_MODEL}.")
    p.add_argument("--instructions", default=None,
                   help="voice-steer prompt (gpt-4o-mini-tts only). "
                        "e.g. 'measured, slightly low cadence, no exclamation'")
    p.add_argument("--max-chars-per-chunk", type=int, default=DEFAULT_MAX_CHARS,
                   help=f"chunk size for the openai per-call limit. default {DEFAULT_MAX_CHARS}.")
    p.add_argument("--speed", type=float, default=1.0,
                   help="playback speed 0.25-4.0. default 1.0.")
    p.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC,
                   help=f"per-call api timeout. default {DEFAULT_TIMEOUT_SEC}.")
    p.add_argument("--config", type=Path, default=Path(".loswf/config.yaml"),
                   help="optional config file for pronunciation overrides "
                        "(article_audio.pronunciations). default .loswf/config.yaml.")
    p.add_argument("--no-pronunciations", action="store_true",
                   help="skip pronunciation substitutions. The default rules "
                        "(loswf → 'low swiff') prevent gpt-4o-mini-tts from "
                        "mispronouncing brand words; disable when debugging or "
                        "when reading content that shouldn't be remapped.")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("generate_article_audio: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    md_path: Path = args.md
    if not md_path.exists():
        print(f"generate_article_audio: --md not found: {md_path}", file=sys.stderr)
        return 2

    out_path: Path = args.out if args.out else md_path.parent / "audio.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw = md_path.read_text(encoding="utf-8")
    plain = markdown_to_plain(raw)
    if not plain:
        print(f"generate_article_audio: nothing to read after stripping markdown: {md_path}",
              file=sys.stderr)
        return 2

    # Apply pronunciation substitutions BEFORE chunking so a chunk
    # boundary doesn't split a substituted phrase.
    pronunciation_counts: dict[str, int] = {}
    if not args.no_pronunciations:
        overrides = _load_pronunciation_overrides(args.config)
        rules = _compile_pronunciation_rules(overrides)
        plain, pronunciation_counts = apply_pronunciations(plain, rules)

    chunks = chunk_text(plain, args.max_chars_per_chunk)
    if not chunks:
        print(f"generate_article_audio: chunking produced no output", file=sys.stderr)
        return 2

    started = time.monotonic()
    started_iso = _iso_now()
    total_chars = sum(len(c) for c in chunks)
    audio_bytes = bytearray()
    per_chunk_meta: list[dict] = []

    for idx, chunk in enumerate(chunks):
        chunk_started = time.monotonic()
        bytes_ = _tts_call(
            chunk,
            model=args.model,
            voice=args.voice,
            fmt=DEFAULT_FORMAT,
            speed=args.speed,
            instructions=args.instructions,
            api_key=api_key,
            timeout=args.timeout_sec,
        )
        audio_bytes.extend(bytes_)
        per_chunk_meta.append({
            "index": idx,
            "chars": len(chunk),
            "bytes": len(bytes_),
            "duration_sec": round(time.monotonic() - chunk_started, 2),
        })

    out_path.write_bytes(bytes(audio_bytes))
    finished = time.monotonic()
    finished_iso = _iso_now()

    char_cost = _COST_PER_1M_CHARS.get(args.model, 0.0) * total_chars / 1_000_000
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "id": str(uuid.uuid4()),
        "started_at": started_iso,
        "finished_at": finished_iso,
        "wall_seconds": round(finished - started, 2),
        "md_path": str(md_path.resolve()),
        "out_path": str(out_path.resolve()),
        "out_size_bytes": out_path.stat().st_size,
        "model": args.model,
        "voice": args.voice,
        "format": DEFAULT_FORMAT,
        "speed": args.speed,
        "instructions": args.instructions,
        "char_count": total_chars,
        "chunk_count": len(chunks),
        "chunks": per_chunk_meta,
        "estimated_cost_usd": round(char_cost, 4),
        "plain_sha256": hashlib.sha256(plain.encode("utf-8")).hexdigest(),
        "pronunciations_applied": pronunciation_counts,
        "pronunciations_skipped": bool(args.no_pronunciations),
    }
    receipt_path = out_path.with_suffix(out_path.suffix + ".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "out": str(out_path),
        "receipt": str(receipt_path),
        "wall_seconds": round(finished - started, 2),
        "chars": total_chars,
        "chunks": len(chunks),
        "size_bytes": out_path.stat().st_size,
        "estimated_cost_usd": round(char_cost, 4),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
