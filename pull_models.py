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
from pathlib import Path
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
    """Return total visible NVIDIA VRAM in MB, or 0 when no GPU is visible here."""
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


def detect_system_ram_mb() -> int:
    """Return visible system RAM in MB.

    In containers, prefer the cgroup memory limit when one is set; otherwise fall
    back to host-visible MemTotal from /proc/meminfo.
    """
    cgroup_paths = [
        "/sys/fs/cgroup/memory.max",  # cgroup v2
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",  # cgroup v1
    ]

    for path in cgroup_paths:
        try:
            raw = Path(path).read_text(encoding="utf-8").strip()
            if raw and raw != "max":
                limit_bytes = int(raw)
                # Ignore effectively-unlimited sentinel values.
                if 0 < limit_bytes < (1 << 60):
                    return limit_bytes // (1024 * 1024)
        except Exception:
            pass

    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) // 1024
    except Exception:
        pass

    return 0


def _auto_select_tier(vram_mb: int, ram_mb: int) -> tuple[str, str]:
    """Pick a model tier and return the decision reason."""
    if vram_mb >= 8000:
        return "large", f"GPU detected ({vram_mb} MB VRAM)"
    if vram_mb >= 3500:
        return "default", f"GPU detected ({vram_mb} MB VRAM)"

    # In containerized setups the resolver may run outside the GPU-enabled Ollama
    # process, so use visible system RAM as a fallback instead of always forcing
    # the tiny tier.
    if ram_mb >= 12000:
        return "default", f"no GPU visible here; falling back to system RAM ({ram_mb} MB)"

    return "tiny", (
        f"no GPU visible here; system RAM fallback is limited ({ram_mb} MB)"
        if ram_mb
        else "no GPU or RAM data available"
    )


def resolve_chat_model() -> str:
    """If CHAT_MODEL is 'auto', pick the best model for available hardware."""
    if CHAT_MODEL != "auto":
        return CHAT_MODEL

    vram = detect_vram_mb()
    ram = detect_system_ram_mb()
    tier, reason = _auto_select_tier(vram, ram)

    model = MODEL_TIERS[tier]
    details = []
    if vram:
        details.append(f"VRAM {vram} MB")
    if ram:
        details.append(f"RAM {ram} MB")
    hardware = ", ".join(details) if details else "no hardware metrics visible"
    print(f"  🔍  Hardware: {hardware} → {reason} → tier '{tier}' → {model}", flush=True)
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
