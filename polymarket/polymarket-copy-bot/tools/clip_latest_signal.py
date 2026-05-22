"""Copy the latest SIGNAL's market URL to the OS clipboard.

The watcher (DryRunExecutor) appends every OPEN signal as a JSON line to
SIGNALS_JSONL_PATH. This tool reads the last line and pushes the market
URL onto the clipboard so the operator can immediately paste it into a
browser tab to trade by hand.

Run interactively (NOT in the background watcher process):
    python tools/clip_latest_signal.py

Optional: pick the Nth-from-last signal (default 1 = latest)
    python tools/clip_latest_signal.py --offset 3
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def read_last_signal(path: Path, offset: int = 1) -> dict | None:
    """Return the JSON record `offset` lines from the end of the file, or
    None if the file does not have that many lines. offset=1 is the latest.
    """
    if not path.exists() or path.stat().st_size == 0:
        return None
    # Cheap and correct for typical signal volume (well under 10k entries):
    # read all lines, take the one we want.
    with path.open(encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    if offset > len(lines):
        return None
    return json.loads(lines[-offset])


def push_to_clipboard(text: str) -> bool:
    """Best-effort OS clipboard push. Returns True if subprocess returned 0."""
    if sys.platform == "win32":
        # PowerShell Set-Clipboard ships with all modern Windows.
        # `--%` would force-stop parsing, but we keep -Value explicit.
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Set-Clipboard", "-Value", text],
                check=True, timeout=5,
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    if sys.platform == "darwin":
        try:
            subprocess.run(["pbcopy"], input=text.encode(),
                           check=True, timeout=5)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    # Linux: try xclip then xsel
    for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"]):
        try:
            subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="data/signals.jsonl",
                        help="path to signals.jsonl")
    parser.add_argument("--offset", type=int, default=1,
                        help="1=latest, 2=second-latest, ...")
    parser.add_argument("--field", default="url",
                        choices=["url", "market_id", "title"],
                        help="what to copy (default: url)")
    args = parser.parse_args(argv)
    rec = read_last_signal(Path(args.path), offset=args.offset)
    if rec is None:
        print(f"no signal at offset={args.offset} in {args.path}",
              file=sys.stderr)
        return 2
    value = rec.get(args.field, "")
    if not value:
        print(f"signal has no '{args.field}' field", file=sys.stderr)
        return 2
    ok = push_to_clipboard(value)
    short_trader = rec.get("source_trader", "?")[:12] + "..."
    title = rec.get("title", "")[:50]
    side = rec.get("side", "?")
    price = rec.get("price", 0)
    print(f"{'copied' if ok else 'WOULD copy'}: {value}")
    print(f"  trader  {short_trader}")
    print(f"  market  {title}")
    print(f"  action  BUY {side} @ ${price:.4f}")
    if not ok:
        print("  (clipboard push failed -- value printed above)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
