#!/usr/bin/env python3
"""
gia — DevOps & Endpoint Security AI Expert
RAG-powered CLI agent using Ollama + local SQLite vector store.
"""

import os
import sys
import json
import math
import struct
import sqlite3
import readline
import threading
import time
import requests

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from rich.style import Style

# ── Configuration ─────────────────────────────────────────────────────────────
from config import (
    DB_PATH, OLLAMA_URL, EMBED_MODEL, CHAT_MODEL,
    TOP_K, SIM_THRESHOLD, HISTORY_TURNS, WRAP_WIDTH, CODE_STYLE,
)

# ── Persona ────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are gia, a principal-level expert in DevOps engineering and Endpoint Security.
Your background spans:
  - Infrastructure automation (Kubernetes, Docker, Ansible, Terraform)
  - Linux systems engineering and hardening
  - Endpoint Detection & Response (EDR) architecture and analysis
  - Threat detection frameworks: MITRE ATT&CK, Sigma, YARA
  - Incident response and NIST security guidelines (SP 800-61, SP 800-83, SP 800-137)
  - eBPF-based kernel-level observability and security sensors
  - Continuous monitoring and malware analysis

Respond using ONLY the provided context from the knowledge base.
When the context is insufficient, say so directly — never fabricate technical details.
Communicate like a hands-on expert: give working commands, concrete examples, and precise explanations.
Use markdown formatting (code blocks, bullet lists) where it improves clarity.
Be direct, dense, and professional. Avoid filler phrases."""

# ── Rich console ───────────────────────────────────────────────────────────────
console = Console()

# ── ANSI Colours (kept for prompt line + minimal legacy use) ───────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    CYAN    = "\033[36m"
    WHITE   = "\033[97m"
    RED     = "\033[31m"
    BCYAN   = "\033[96m"
    BBLUE   = "\033[94m"
    BGREEN  = "\033[92m"
    BYELLOW = "\033[93m"

def c(code: str, text: str) -> str:
    return f"{code}{text}{C.RESET}"

# ── Terminal helpers ───────────────────────────────────────────────────────────
def _term_width() -> int:
    return console.width

def clear_screen():
    os.system("clear")

# ── Spinner ────────────────────────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label: str):
        self._label  = label
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r  {c(C.BCYAN, frame)}  {c(C.DIM, self._label)}  ")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        w = _term_width()
        sys.stdout.write("\r" + " " * w + "\r")
        sys.stdout.flush()

# ── Embedding & search ─────────────────────────────────────────────────────────
def get_embedding(text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]

def blob_to_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0

def search_chunks(conn: sqlite3.Connection, query_emb: list[float]) -> list[dict]:
    rows = conn.execute(
        "SELECT file_path, category, chunk_index, content, embedding FROM chunks"
    ).fetchall()
    scored = []
    for fp, cat, idx, content, blob in rows:
        sim = cosine_similarity(query_emb, blob_to_embedding(blob))
        if sim >= SIM_THRESHOLD:
            scored.append({
                "file_path":   fp,
                "category":    cat,
                "chunk_index": idx,
                "content":     content,
                "similarity":  sim,
            })
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:TOP_K]

def build_context(results: list[dict]) -> str:
    if not results:
        return "No relevant context found in the knowledge base."
    parts = []
    for r in results:
        src = os.path.basename(r["file_path"])
        parts.append(
            f"[Source: {src} | category: {r['category']} | relevance: {r['similarity']:.3f}]\n"
            f"{r['content']}"
        )
    return "\n\n".join(parts)

# ── Streaming response with live markdown rendering ────────────────────────────
def _build_panel(answer: str, done: bool = False) -> Panel:
    """Build a rich Panel containing the streamed answer as rendered Markdown."""
    md = Markdown(answer, code_theme=CODE_STYLE) if answer else Text("⏳", style="dim")
    subtitle = None if done else "[dim italic]generating…[/]"
    return Panel(
        md,
        title="[bold bright_cyan]gia[/]",
        title_align="left",
        subtitle=subtitle,
        subtitle_align="right",
        border_style="bright_blue",
        padding=(1, 2),
        expand=True,
    )

def stream_answer(
    conn: sqlite3.Connection,
    question: str,
    conversation: list[dict],
) -> tuple[str, list[dict], dict]:
    """Embed → retrieve → stream with live-updating markdown panel."""
    with Spinner("Searching knowledge base…"):
        query_emb = get_embedding(question)
        results   = search_chunks(conn, query_emb)
        context   = build_context(results)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation[-(HISTORY_TURNS * 2):]:
        messages.append(msg)
    messages.append({
        "role":    "user",
        "content": f"Knowledge base context:\n{context}\n\nQuestion: {question}",
    })

    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": CHAT_MODEL, "messages": messages, "stream": True},
        timeout=600,
        stream=True,
    )
    resp.raise_for_status()

    answer     = ""
    final_data = {}

    with Live(_build_panel(""), console=console, refresh_per_second=8) as live:
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                answer += token
                live.update(_build_panel(answer))
            if chunk.get("done"):
                final_data = chunk
                break
        # Final render with "done" state (no subtitle)
        live.update(_build_panel(answer, done=True))

    return answer, results, final_data

# ── Source panel ───────────────────────────────────────────────────────────────
def _sim_style(sim: float) -> str:
    if sim >= 0.90: return "bold bright_green"
    if sim >= 0.80: return "green"
    if sim >= 0.70: return "yellow"
    if sim >= 0.60: return "bright_yellow"
    return "dim"

def _sim_bar(sim: float, width: int = 10) -> str:
    filled = round(sim * width)
    return "█" * filled + "░" * (width - filled)

def print_sources(results: list[dict]):
    if not results:
        return
    tbl = Table(show_header=False, border_style="dim", box=None, padding=(0, 1))
    tbl.add_column("bar", width=12)
    tbl.add_column("score", width=7)
    tbl.add_column("source")
    for r in results:
        fname = os.path.basename(r["file_path"])
        cat   = r["category"]
        sim   = r["similarity"]
        style = _sim_style(sim)
        tbl.add_row(
            Text(_sim_bar(sim), style=style),
            Text(f"{sim:.3f}", style=style),
            Text(f"{cat}/{fname}", style="white"),
        )
    console.print(Panel(
        tbl,
        title="[dim]Sources[/]",
        title_align="left",
        border_style="dim",
        padding=(0, 1),
    ))

# ── Stats footer ───────────────────────────────────────────────────────────────
def print_stats(final_data: dict, elapsed: float):
    eval_count   = final_data.get("eval_count", 0)
    eval_ns      = final_data.get("eval_duration", 1)
    prompt_count = final_data.get("prompt_eval_count", 0)
    prompt_ns    = final_data.get("prompt_eval_duration", 1)
    gen_tps      = eval_count / (eval_ns / 1e9) if eval_ns else 0
    prompt_tps   = prompt_count / (prompt_ns / 1e9) if prompt_ns else 0
    total_tokens = prompt_count + eval_count
    console.print(
        f"  [dim]tokens:[/] [bright_yellow]{total_tokens}[/]"
        f"  [dim]gen:[/] [bright_yellow]{gen_tps:.0f} tok/s[/]"
        f"  [dim]prompt:[/] [bright_yellow]{prompt_tps:.0f} tok/s[/]"
        f"  [dim]time:[/] [bright_yellow]{elapsed:.1f}s[/]"
    )

# ── Banner ─────────────────────────────────────────────────────────────────────
def print_banner(chunk_count: int, cats: list[tuple]):
    cat_parts = "  ".join(f"[cyan]{cat}[/] [dim]{n}[/]" for cat, n in cats)
    body = (
        f"[bold bright_cyan]g i a[/]  ·  DevOps & Endpoint Security Expert\n"
        f"[dim]model: {CHAT_MODEL}  ·  {chunk_count:,} knowledge chunks indexed[/]\n\n"
        f"{cat_parts}\n\n"
        f"[dim]commands:[/]  [cyan]help[/]  ·  [cyan]sources[/]  ·  "
        f"[cyan]clear[/]  ·  [cyan]history[/]  ·  [cyan]quit[/]"
    )
    console.print()
    console.print(Panel(body, border_style="bright_blue", padding=(1, 2), expand=True))

def print_help():
    tbl = Table(show_header=False, border_style="dim", box=None, padding=(0, 1))
    tbl.add_column("cmd", style="cyan", width=14)
    tbl.add_column("desc", style="dim")
    for cmd, desc in [
        ("help",       "Show this reference"),
        ("sources",    "Show knowledge sources cited in the last answer"),
        ("clear",      "Clear screen and reset conversation history"),
        ("history",    "Replay this session's conversation"),
        ("quit / q",   "Exit gia"),
        ("<question>", "Ask anything about DevOps or Endpoint Security"),
    ]:
        tbl.add_row(cmd, desc)
    console.print()
    console.print(Panel(tbl, title="[bold bright_cyan]gia — Command Reference[/]",
                        title_align="left", border_style="bright_blue", padding=(1, 1)))
    console.print()

# ── Main REPL ──────────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DB_PATH):
        console.print("\n  [red]✗ Knowledge database not found. Run vectorize.py first.[/]\n")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    if chunk_count == 0:
        console.print("\n  [red]✗ Knowledge database is empty. Run vectorize.py first.[/]\n")
        sys.exit(1)

    # Guard: ensure the DB was embedded with the same model we're using now
    row = conn.execute("SELECT value FROM meta WHERE key = 'embed_model'").fetchone()
    if row and row[0] != EMBED_MODEL:
        console.print(f"\n  [red]✗ Embed model mismatch![/]")
        console.print(f"    [dim]DB built with : {row[0]}[/]")
        console.print(f"    [dim]Currently set : {EMBED_MODEL}[/]")
        console.print(f"\n    [dim]Rebuild:  rm knowledge.db && python3 vectorize.py[/]\n")
        sys.exit(1)

    cats = conn.execute(
        "SELECT category, COUNT(*) FROM chunks GROUP BY category ORDER BY category"
    ).fetchall()

    clear_screen()
    print_banner(chunk_count, cats)

    conversation = []
    last_results = []
    turn         = 0

    while True:
        try:
            prefix   = c(C.BOLD + C.BCYAN, "  you") + c(C.DIM, f"  #{turn + 1}  ❯  ")
            question = input(prefix).strip()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n\n  [dim]Session ended.[/]\n")
            break

        if not question:
            continue

        cmd = question.lower()

        if cmd in ("quit", "exit", "q"):
            console.print(f"\n  [dim]Session ended.[/]\n")
            break

        if cmd == "help":
            print_help()
            continue

        if cmd == "clear":
            conversation.clear()
            last_results = []
            turn = 0
            clear_screen()
            print_banner(chunk_count, cats)
            console.print("[dim]  Conversation cleared.[/]\n")
            continue

        if cmd == "sources":
            if last_results:
                print_sources(last_results)
            else:
                console.print("\n  [dim]No previous query results.[/]\n")
            continue

        if cmd == "history":
            if not conversation:
                console.print("\n  [dim]No history yet.[/]\n")
            else:
                console.print()
                console.rule(style="bright_blue")
                for msg in conversation:
                    if msg["role"] == "user":
                        label = "[bold bright_cyan]  you ❯[/]"
                    else:
                        label = "[bold bright_green]  gia ❯[/]"
                    preview = msg["content"][:220].replace("\n", " ")
                    if len(msg["content"]) > 220:
                        preview += "…"
                    console.print(f"{label}  [dim]{preview}[/]")
                console.rule(style="bright_blue")
                console.print()
            continue

        # ── RAG turn ──────────────────────────────────────────────────────────
        console.rule(style="dim")
        t_start = time.perf_counter()
        try:
            answer, last_results, final_data = stream_answer(conn, question, conversation)
            elapsed = time.perf_counter() - t_start

            conversation.append({"role": "user",      "content": question})
            conversation.append({"role": "assistant", "content": answer})
            turn += 1

            print_sources(last_results)
            print_stats(final_data, elapsed)
            console.print()

        except requests.exceptions.ConnectionError:
            console.print("\n  [red]✗ Cannot connect to Ollama. Is it running?[/]\n")
        except Exception as e:
            console.print(f"\n  [red]✗ {e}[/]\n")

    conn.close()


if __name__ == "__main__":
    main()
