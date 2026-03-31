#!/usr/bin/env python3
"""
gia — shared configuration
All runtime-tunable settings for vectorize.py, chat.py, and benchmark.py.
Override any value via the corresponding environment variable.
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# ── Paths ──────────────────────────────────────────────────────────────────────
DB_PATH       = os.path.join(_HERE, "knowledge.db")
KNOWLEDGE_DIR = os.path.join(_HERE, "knowledge")

# ── Ollama endpoints & models ──────────────────────────────────────────────────
OLLAMA_URL  = os.environ.get("OLLAMA_URL",  "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL  = os.environ.get("CHAT_MODEL",  "phi4-mini:3.8b")

# ── Chunking (vectorize.py) ────────────────────────────────────────────────────
CHUNK_SIZE    = int(os.environ.get("CHUNK_SIZE",    "500"))  # approx chars per chunk
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "50"))   # overlap between chunks

# ── Retrieval (chat.py) ────────────────────────────────────────────────────────
TOP_K         = int(os.environ.get("TOP_K",                  "5"))
SIM_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.3"))
HISTORY_TURNS = int(os.environ.get("HISTORY_TURNS",          "8"))   # user+assistant pairs kept

# ── Display (chat.py) ──────────────────────────────────────────────────────────
WRAP_WIDTH = int(os.environ.get("WRAP_WIDTH", "90"))
CODE_STYLE = os.environ.get("CODE_STYLE",     "monokai")  # pygments theme: dracula, native, one-dark

# ── Benchmark (benchmark.py) ───────────────────────────────────────────────────
BENCH_MAX_TOKENS = int(os.environ.get("BENCH_MAX_TOKENS", "100"))
