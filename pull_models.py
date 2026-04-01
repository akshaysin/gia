#!/usr/bin/env python3
"""
Startup helper: waits for Ollama to be ready, then ensures the required
embedding and chat models are present — pulling them automatically if not.

Called by entrypoint.sh before the main command is exec'd.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

from config import CHAT_MODEL, EMBED_MODEL, OLLAMA_URL, MODEL_TIERS

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


# ── Hardware detection & model auto-selection ──────────────────────────────────
def detect_vram_mb() -> int:
    """Query Ollama /api/ps for available GPU VRAM. Returns 0 if no GPU."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=5) as resp:
            data = json.loads(resp.read())
        # Ollama reports per-model GPU memory; if nothing loaded, try /api/show
        # Fall back to checking nvidia-smi via a simple heuristic
    except Exception:
        pass

    # Try parsing nvidia-smi (works outside containers too)
    try:
        import subprocess
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            timeout=5, text=True,
        )
        total_mb = sum(int(line.strip()) for line in out.strip().split("\n") if line.strip())
        return total_mb
    except Exception:
        return 0


def resolve_chat_model() -> str:
    """If CHAT_MODEL is 'auto', pick the best model for available hardware."""
    if CHAT_MODEL != "auto":
        return CHAT_MODEL

    vram = detect_vram_mb()

    if vram >= 8000:
        tier = "large"
    elif vram >= 3500:
        tier = "default"
    else:
        tier = "tiny"

    model = MODEL_TIERS[tier]
    vram_str = f"{vram} MB VRAM" if vram else "no GPU detected"
    print(f"  🔍  Hardware: {vram_str} → tier '{tier}' → {model}", flush=True)
    return model


if __name__ == "__main__":
    wait_for_ollama()
    print("  🔍  Checking required models…", flush=True)
    chat_model = resolve_chat_model()
    pull_if_missing(EMBED_MODEL)
    pull_if_missing(chat_model)
    # Write resolved model so downstream scripts pick it up
    if CHAT_MODEL == "auto":
        os.environ["CHAT_MODEL"] = chat_model
    print()
