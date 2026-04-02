#!/usr/bin/env python3
"""
Runtime health check for gia.
Reports connectivity, model selection, and visible resources.
"""

import json
import sys
import urllib.error
import urllib.request

from config import CHAT_MODEL, EMBED_MODEL, GIA_PROFILE, OLLAMA_URL
from pull_models import _model_present, detect_system_ram_mb, detect_vram_mb, resolve_chat_model


def _tags_url() -> str:
    return f"{OLLAMA_URL}/api/tags"


def _format_mb(value: int) -> str:
    if not value:
        return "unknown"
    return f"{value:,} MB"


def _launch_mode(vram_mb: int) -> str:
    return "GPU-visible" if vram_mb else "CPU-only"


def _profile_name() -> str:
    if GIA_PROFILE:
        return GIA_PROFILE
    if CHAT_MODEL == "auto":
        return "auto"
    return "custom"


def check_ollama() -> tuple[bool, list[str], str]:
    try:
        with urllib.request.urlopen(_tags_url(), timeout=5) as resp:
            payload = json.loads(resp.read())
        models = [m["name"] for m in payload.get("models", [])]
        return True, models, "reachable"
    except urllib.error.URLError as exc:
        return False, [], str(exc.reason)
    except Exception as exc:
        return False, [], str(exc)


def main() -> int:
    ok, installed, detail = check_ollama()
    vram_mb = detect_vram_mb()
    ram_mb = detect_system_ram_mb()
    resolved_chat_model = resolve_chat_model()

    print("gia doctor")
    print("=" * 72)
    print(f"Ollama URL      : {OLLAMA_URL}")
    print(f"Ollama status   : {'ok' if ok else 'unreachable'} ({detail})")
    print(f"Launch mode     : {_launch_mode(vram_mb)}")
    print(f"Visible RAM     : {_format_mb(ram_mb)}")
    print(f"Visible VRAM    : {_format_mb(vram_mb)}")
    print(f"Profile         : {_profile_name()}")
    print(f"Chat model      : {resolved_chat_model}")
    print(f"Embed model     : {EMBED_MODEL}")

    if ok:
        chat_present = _model_present(installed, resolved_chat_model)
        embed_present = _model_present(installed, EMBED_MODEL)
        print(f"Chat installed  : {'yes' if chat_present else 'no'}")
        print(f"Embed installed : {'yes' if embed_present else 'no'}")
    else:
        print("Chat installed  : unknown")
        print("Embed installed : unknown")

    print("=" * 72)

    if not vram_mb:
        print("Note: CPU-only mode is expected on macOS/Windows systems without NVIDIA access.")
        if ram_mb and ram_mb < 8192:
            print("Warning: visible memory is low. For Docker Desktop, allocate at least 8 GB if possible.")
        else:
            print("Tip: if responses feel slow on Docker Desktop, increase the VM memory allocation.")

    if not ok:
        print("Warning: Ollama is not reachable. Start the stack first, then rerun `make doctor`.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())