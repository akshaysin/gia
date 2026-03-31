#!/usr/bin/env python3
"""
gia — DevOps & Endpoint Security AI Expert
RAG-powered CLI agent using Ollama + local SQLite vector store.
"""

import os
import re
import sys
import json
import math
import struct
import sqlite3
import readline
import threading
import time
import requests

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, TextLexer
    from pygments.formatters import Terminal256Formatter
    from pygments.util import ClassNotFound
    _PYGMENTS = True
except ImportError:
    _PYGMENTS = False

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

# ── ANSI Colours ──────────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    CYAN    = "\033[36m"
    BLUE    = "\033[34m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    WHITE   = "\033[97m"
    MAGENTA = "\033[35m"
    BCYAN   = "\033[96m"
    BBLUE   = "\033[94m"
    BGREEN  = "\033[92m"
    BYELLOW = "\033[93m"

def c(code: str, text: str) -> str:
    return f"{code}{text}{C.RESET}"

# ── Terminal helpers ───────────────────────────────────────────────────────────
def _term_width() -> int:
    try:
        return min(os.get_terminal_size().columns, WRAP_WIDTH)
    except Exception:
        return WRAP_WIDTH

def print_hr(ch: str = "─", colour: str = C.DIM):
    print(c(colour, ch * _term_width()))

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
        sys.stdout.write("\r" + " " * _term_width() + "\r")
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

# ── Markdown renderer ─────────────────────────────────────────────────────────
# Inline patterns applied left-to-right (order matters: backtick before bold)
_INLINE_RE = [
    (re.compile(r'`([^`]+)`'),             lambda m: c(C.BYELLOW, m.group(1))),
    (re.compile(r'\*\*([^*]+)\*\*'),       lambda m: c(C.BOLD + C.WHITE, m.group(1))),
    (re.compile(r'\*([^*]+)\*'),           lambda m: c(C.DIM + C.WHITE, m.group(1))),
    (re.compile(r'\[([^\]]+)\]\([^)]+\)'), lambda m: c(C.BBLUE, m.group(1))),
]

def _render_inline(text: str) -> str:
    for pat, sub in _INLINE_RE:
        text = pat.sub(sub, text)
    return text

def _highlight_block(code: str, lang: str) -> str:
    if _PYGMENTS:
        try:
            lexer = get_lexer_by_name(lang.strip() or "text", stripall=False)
        except ClassNotFound:
            lexer = TextLexer()
        fmt        = Terminal256Formatter(style=CODE_STYLE)
        highlighted = highlight(code, lexer, fmt).rstrip("\n")
        return "\n".join("    " + ln for ln in highlighted.splitlines())
    # Fallback: plain yellow
    return "\n".join("    " + c(C.BYELLOW, ln) for ln in code.splitlines())

def render_markdown(text: str) -> None:
    """Print a markdown string with ANSI highlighting to stdout."""
    w     = _term_width()
    lines = text.splitlines()
    i     = 0
    while i < len(lines):
        line = lines[i]

        # Fenced code block  ``` [lang] ... ```
        fence = re.match(r'^(```+|~~~+)\s*(\S*)', line)
        if fence:
            fence_tok = fence.group(1)[:3]
            lang      = fence.group(2) or "text"
            code_buf  = []
            i += 1
            while i < len(lines) and not lines[i].startswith(fence_tok):
                code_buf.append(lines[i])
                i += 1
            label   = lang.upper() if lang else "CODE"
            bar_pad = max(w - len(label) - 8, 0)
            print(c(C.DIM, "  ┌─ ") + c(C.BOLD + C.BCYAN, label) +
                  c(C.DIM, " " + "─" * bar_pad + "┐"))
            print(_highlight_block("\n".join(code_buf), lang))
            print(c(C.DIM, "  └" + "─" * (w - 4) + "┘"))
            i += 1   # skip closing fence
            continue

        # ATX headings  # / ## / ###
        heading = re.match(r'^(#{1,3})\s+(.*)', line)
        if heading:
            lvl  = len(heading.group(1))
            body = heading.group(2)
            colour = {1: C.BOLD + C.BCYAN, 2: C.BOLD + C.BBLUE, 3: C.BOLD + C.CYAN}[lvl]
            print(c(colour, "  " + "#" * lvl + " " + body))
            i += 1
            continue

        # Horizontal rule  --- / ***
        if re.match(r'^\s*[-*]{3,}\s*$', line):
            print(c(C.DIM, "  " + "─" * (w - 2)))
            i += 1
            continue

        # Bullet list  - / * / +
        bullet = re.match(r'^(\s*)[-*+]\s+(.*)', line)
        if bullet:
            indent = len(bullet.group(1))
            print("  " + " " * indent + c(C.CYAN, "●") + "  " +
                  _render_inline(bullet.group(2)))
            i += 1
            continue

        # Numbered list  1. / 2.
        numbered = re.match(r'^(\s*)(\d+)\.\s+(.*)', line)
        if numbered:
            indent = len(numbered.group(1))
            print("  " + " " * indent + c(C.CYAN, numbered.group(2) + ".") +
                  "  " + _render_inline(numbered.group(3)))
            i += 1
            continue

        # Blank line
        if line.strip() == "":
            print()
            i += 1
            continue

        # Plain prose
        print("  " + _render_inline(line))
        i += 1


# ── Streaming response ─────────────────────────────────────────────────────────
def stream_answer(
    conn: sqlite3.Connection,
    question: str,
    conversation: list[dict],
) -> tuple[str, list[dict], dict]:
    """Embed → retrieve → stream generation. Returns (answer, results, stats)."""
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

    # Collect all tokens silently; spinner shows live count
    answer     = ""
    final_data = {}

    with Spinner("Generating…") as sp:
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                answer    += token
                sp._label  = f"Generating…  {len(answer.split())} words"
            if chunk.get("done"):
                final_data = chunk
                break

    # Render the buffered response with full markdown highlighting
    print(f"\n{c(C.BOLD + C.BCYAN, '  gia')}\n")
    render_markdown(answer)
    print()
    return answer, results, final_data

# ── Source panel ───────────────────────────────────────────────────────────────
def _sim_colour(sim: float) -> str:
    if sim >= 0.90: return C.BGREEN
    if sim >= 0.80: return C.GREEN
    if sim >= 0.70: return C.YELLOW
    if sim >= 0.60: return C.BYELLOW
    return C.DIM

def _sim_bar(sim: float, width: int = 10) -> str:
    filled = round(sim * width)
    return c(_sim_colour(sim), "█" * filled + "░" * (width - filled))

def print_sources(results: list[dict]):
    if not results:
        return
    w = _term_width()
    print()
    print(c(C.DIM, "  ┌─ Sources " + "─" * (w - 13) + "┐"))
    for r in results:
        fname = os.path.basename(r["file_path"])
        cat   = r["category"]
        sim   = r["similarity"]
        bar   = _sim_bar(sim)
        score = c(_sim_colour(sim), f"{sim:.3f}")
        src   = f"{c(C.DIM, cat + '/')}{c(C.WHITE, fname)}"
        print(f"  {c(C.DIM, '│')}  {bar}  {score}  {src}")
    print(c(C.DIM, "  └" + "─" * (w - 4) + "┘"))

# ── Stats footer ───────────────────────────────────────────────────────────────
def print_stats(final_data: dict, elapsed: float):
    eval_count   = final_data.get("eval_count", 0)
    eval_ns      = final_data.get("eval_duration", 1)
    prompt_count = final_data.get("prompt_eval_count", 0)
    prompt_ns    = final_data.get("prompt_eval_duration", 1)
    gen_tps      = eval_count / (eval_ns / 1e9) if eval_ns else 0
    prompt_tps   = prompt_count / (prompt_ns / 1e9) if prompt_ns else 0
    total_tokens = prompt_count + eval_count
    print(
        f"\n  "
        f"{c(C.DIM, 'tokens:')} {c(C.BYELLOW, str(total_tokens))}"
        f"  {c(C.DIM, 'gen:')} {c(C.BYELLOW, f'{gen_tps:.0f} tok/s')}"
        f"  {c(C.DIM, 'prompt:')} {c(C.BYELLOW, f'{prompt_tps:.0f} tok/s')}"
        f"  {c(C.DIM, 'time:')} {c(C.BYELLOW, f'{elapsed:.1f}s')}"
        f"\n"
    )

# ── Banner ─────────────────────────────────────────────────────────────────────
def print_banner(chunk_count: int, cats: list[tuple]):
    w = _term_width()
    print()
    print(c(C.BBLUE, "╔" + "═" * (w - 2) + "╗"))
    line1 = "g i a   ·   DevOps & Endpoint Security Expert"
    line2 = f"model: {CHAT_MODEL}   ·   {chunk_count:,} knowledge chunks indexed"
    print(c(C.BBLUE, "║") + c(C.BOLD + C.BCYAN, line1.center(w - 2)) + c(C.BBLUE, "║"))
    print(c(C.BBLUE, "║") + c(C.DIM,             line2.center(w - 2)) + c(C.BBLUE, "║"))
    print(c(C.BBLUE, "╠" + "═" * (w - 2) + "╣"))
    # Category breakdown in banner
    cat_line = "  ".join(f"{c(C.CYAN, cat)} {c(C.DIM, str(n))}" for cat, n in cats)
    print(c(C.BBLUE, "║") + f" {cat_line}".ljust(w - 1) + c(C.BBLUE, "║"))
    print(c(C.BBLUE, "╚" + "═" * (w - 2) + "╝"))
    print()
    cmds = ["help", "sources", "clear", "history", "quit"]
    cmd_row = c(C.DIM, "  Commands: ") + c(C.DIM, "  ·  ").join(c(C.CYAN, x) for x in cmds)
    print(cmd_row)
    print()

def print_help():
    items = [
        ("help",       "Show this reference"),
        ("sources",    "Show knowledge sources cited in the last answer"),
        ("clear",      "Clear screen and reset conversation history"),
        ("history",    "Replay this session's conversation"),
        ("quit / q",   "Exit gia"),
        ("<question>", "Ask anything about DevOps or Endpoint Security"),
    ]
    print()
    print_hr("─", C.BBLUE)
    print(c(C.BOLD + C.BCYAN, "  gia — Command Reference"))
    print_hr("─", C.BBLUE)
    for cmd, desc in items:
        print(f"  {c(C.CYAN, cmd.ljust(14))}  {c(C.DIM, desc)}")
    print_hr("─", C.BBLUE)
    print()

# ── Main REPL ──────────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DB_PATH):
        print(c(C.RED, "\n  ✗ Knowledge database not found. Run vectorize.py first.\n"))
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    if chunk_count == 0:
        print(c(C.RED, "\n  ✗ Knowledge database is empty. Run vectorize.py first.\n"))
        sys.exit(1)

    # Guard: ensure the DB was embedded with the same model we're using now
    row = conn.execute("SELECT value FROM meta WHERE key = 'embed_model'").fetchone()
    if row and row[0] != EMBED_MODEL:
        print(c(C.RED, f"\n  ✗ Embed model mismatch!"))
        print(c(C.DIM, f"    DB built with : {row[0]}"))
        print(c(C.DIM, f"    Currently set : {EMBED_MODEL}"))
        print(c(C.DIM, f"\n    Rebuild:  rm knowledge.db && python3 vectorize.py\n"))
        sys.exit(1)

    cats = conn.execute(
        "SELECT category, COUNT(*) FROM chunks GROUP BY category ORDER BY category"
    ).fetchall()

    clear_screen()
    print_banner(chunk_count, cats)
    print_hr()
    print()

    conversation = []
    last_results = []
    turn         = 0

    while True:
        try:
            prefix   = c(C.BOLD + C.BCYAN, "  you") + c(C.DIM, f"  #{turn + 1}  ❯  ")
            question = input(prefix).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n{c(C.DIM, '  Session ended.')}\n")
            break

        if not question:
            continue

        cmd = question.lower()

        if cmd in ("quit", "exit", "q"):
            print(f"\n{c(C.DIM, '  Session ended.')}\n")
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
            print_hr()
            print(c(C.DIM, "\n  Conversation cleared.\n"))
            continue

        if cmd == "sources":
            if last_results:
                print_sources(last_results)
            else:
                print(c(C.DIM, "\n  No previous query results.\n"))
            print()
            continue

        if cmd == "history":
            if not conversation:
                print(c(C.DIM, "\n  No history yet.\n"))
            else:
                print()
                print_hr("─", C.BBLUE)
                for msg in conversation:
                    if msg["role"] == "user":
                        label = c(C.BOLD + C.BCYAN, "  you ❯")
                    else:
                        label = c(C.BOLD + C.BGREEN, "  gia ❯")
                    preview = msg["content"][:220].replace("\n", " ")
                    if len(msg["content"]) > 220:
                        preview += "…"
                    print(f"{label}  {c(C.DIM, preview)}")
                print_hr("─", C.BBLUE)
            print()
            continue

        # ── RAG turn ──────────────────────────────────────────────────────────
        print_hr()
        t_start = time.perf_counter()
        try:
            answer, last_results, final_data = stream_answer(conn, question, conversation)
            elapsed = time.perf_counter() - t_start

            conversation.append({"role": "user",      "content": question})
            conversation.append({"role": "assistant", "content": answer})
            turn += 1

            print_sources(last_results)
            print_stats(final_data, elapsed)
            print_hr()
            print()

        except requests.exceptions.ConnectionError:
            print(c(C.RED, "\n  ✗ Cannot connect to Ollama. Is it running?\n"))
        except Exception as e:
            print(c(C.RED, f"\n  ✗ {e}\n"))
        finally:
            print()

    conn.close()


if __name__ == "__main__":
    main()
