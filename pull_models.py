#!/usr/bin/env python3
"""
Startup helper: waits for Ollama to be ready, then ensures the required
embedding and chat models are present — pulling them automatically if not.

Called by entrypoint.sh before the main command is exec'd.
"""

import json
import sys
import time
import urllib.error
import urllib.request

from config import CHAT_MODEL, EMBED_MODEL, OLLAMA_URL

PULL_TIMEOUT = 3600  # seconds — large models can take a while on first run


def _tags_url() -> str:
    return f"{OLLAMA_URL}/api/tags"


def _pull_url() -> str:
    return f"{OLLAMA_URL}/api/pull"


# ── Wait for Ollama ────────────────────────────────────────────────────────────
def wait_for_ollama(poll_interval: float = 2.0) -> None:
    sys.stdout.write("\n  ⏳  Waiting for Ollama")
    sys.stdout.flush()
    while True:
        try:
            urllib.request.urlopen(_tags_url(), timeout=3)
            print("  ✓", flush=True)
            return
        except Exception:
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(poll_interval)


# ── Model management ───────────────────────────────────────────────────────────
def installed_models() -> list[str]:
    with urllib.request.urlopen(_tags_url(), timeout=10) as resp:
        return [m["name"] for m in json.loads(resp.read())["models"]]


def pull_if_missing(model: str) -> None:
    try:
        present = installed_models()
    except Exception:
        present = []

    if any(model in n for n in present):
        print(f"  ✓  {model} — already present", flush=True)
        return

    print(f"  ⬇  Pulling {model}…", flush=True)
    req = urllib.request.Request(
        _pull_url(),
        data=json.dumps({"name": model}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    last_pct = -1
    with urllib.request.urlopen(req, timeout=PULL_TIMEOUT) as resp:
        for raw in resp:
            try:
                d = json.loads(raw)
                status    = d.get("status", "")
                completed = d.get("completed", 0)
                total     = d.get("total", 0)
                if total:
                    pct = int(completed * 100 / total)
                    if pct != last_pct:
                        sys.stdout.write(f"\r  ⬇  {model}  {pct:3d}%")
                        sys.stdout.flush()
                        last_pct = pct
                elif status and status not in {"pulling manifest", ""}:
                    print(f"\n     {status}", flush=True)
            except Exception:
                pass

    print(f"\n  ✓  {model} — ready", flush=True)


if __name__ == "__main__":
    wait_for_ollama()
    print("  🔍  Checking required models…", flush=True)
    pull_if_missing(EMBED_MODEL)
    pull_if_missing(CHAT_MODEL)
    print()
