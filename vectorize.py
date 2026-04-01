#!/usr/bin/env python3
"""
Vectorize all markdown and PDF files in the knowledge/ folder.
Chunks the documents, generates embeddings via Ollama, and stores them in a local SQLite DB.
"""

import os
import re
import json
import sqlite3
import struct
import hashlib
import requests

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from config import DB_PATH, KNOWLEDGE_DIR, OLLAMA_URL, EMBED_MODEL, CHUNK_SIZE, CHUNK_OVERLAP, EMBED_DIM


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            category TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            embedding BLOB NOT NULL,
            UNIQUE(file_path, chunk_index)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON chunks(file_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON chunks(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_content_hash ON chunks(content_hash)")
    conn.commit()


def check_embed_model_compat(conn: sqlite3.Connection, model: str):
    """Abort with a clear message if the DB was built with a different embed model or dim."""
    row = conn.execute("SELECT value FROM meta WHERE key = 'embed_model'").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta (key, value) VALUES ('embed_model', ?)", (model,))
        conn.commit()
    elif row[0] != model:
        stored = row[0]
        print(f"\n  ERROR: Embed model mismatch!")
        print(f"    DB was built with : {stored}")
        print(f"    Currently using   : {model}")
        print(f"\n  The stored vectors are incompatible. Rebuild the DB:")
        print(f"    rm knowledge.db && python3 vectorize.py\n")
        raise SystemExit(1)

    # Check dimension compatibility
    dim_str = str(EMBED_DIM) if EMBED_DIM > 0 else "full"
    dim_row = conn.execute("SELECT value FROM meta WHERE key = 'embed_dim'").fetchone()
    if dim_row is None:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('embed_dim', ?)", (dim_str,))
        conn.commit()
    elif dim_row[0] != dim_str:
        print(f"\n  ERROR: Embed dimension mismatch!")
        print(f"    DB was built with : {dim_row[0]}")
        print(f"    Currently set     : {dim_str}")
        print(f"\n  Rebuild the DB:  rm knowledge.db && python3 vectorize.py\n")
        raise SystemExit(1)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, trying to break at paragraph/section boundaries."""
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    chunks = []
    # First split by markdown sections (## headings)
    sections = []
    current_section = ""
    for line in text.split("\n"):
        if line.startswith("## ") and current_section:
            sections.append(current_section)
            current_section = line + "\n"
        else:
            current_section += line + "\n"
    if current_section:
        sections.append(current_section)

    # Now chunk each section if it's too long
    for section in sections:
        if len(section) <= chunk_size:
            if section.strip():
                chunks.append(section.strip())
        else:
            # Sub-chunk within the section
            start = 0
            while start < len(section):
                end = start + chunk_size
                # Try to break at a newline
                if end < len(section):
                    newline_pos = section.rfind("\n", start + chunk_size // 2, end)
                    if newline_pos > start:
                        end = newline_pos + 1
                chunk = section[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                start = end - overlap

    return chunks


def get_embedding(text: str) -> list[float]:
    """Get embedding vector from Ollama, optionally truncated to EMBED_DIM."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=120,
    )
    resp.raise_for_status()
    emb = resp.json()["embeddings"][0]
    if EMBED_DIM > 0:
        emb = emb[:EMBED_DIM]
    return emb


def embedding_to_blob(embedding: list[float]) -> bytes:
    """Pack a list of floats into a binary blob for SQLite storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


SUPPORTED_EXTENSIONS = {".md", ".pdf"}


def extract_pdf_text(fpath: str) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    if not HAS_PYMUPDF:
        print(f"  WARNING: PyMuPDF not installed, skipping {fpath}")
        print("  Install with: pip install pymupdf")
        return ""
    doc = fitz.open(fpath)
    pages = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages.append(text)
    doc.close()
    # Clean up common PDF artifacts
    full_text = "\n\n".join(pages)
    # Collapse excessive whitespace but preserve paragraph breaks
    full_text = re.sub(r"[ \t]+", " ", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    return full_text.strip()


def collect_knowledge_files(root_dir: str) -> list[tuple[str, str, str]]:
    """Walk knowledge dir and return (file_path, category, content) tuples for .md and .pdf files."""
    files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(dirpath, root_dir)
            category = rel if rel != "." else "general"
            if ext == ".pdf":
                content = extract_pdf_text(fpath)
            else:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            if content:
                files.append((fpath, category, content))
            else:
                print(f"  SKIP (no text extracted): {fpath}")
    return files


def main():
    print(f"Knowledge dir: {KNOWLEDGE_DIR}")
    print(f"Database: {DB_PATH}")
    print(f"Ollama: {OLLAMA_URL} | Model: {EMBED_MODEL}")
    print()

    if HAS_PYMUPDF:
        print(f"PDF support: enabled (PyMuPDF {fitz.__version__})")
    else:
        print("PDF support: disabled (install pymupdf for PDF support)")
    print()

    kb_files = collect_knowledge_files(KNOWLEDGE_DIR)
    if not kb_files:
        print("No supported files found in knowledge/")
        return

    print(f"Found {len(kb_files)} file(s):")
    for fpath, cat, content in kb_files:
        ext = os.path.splitext(fpath)[1]
        print(f"  [{cat}] {os.path.basename(fpath)}  ({len(content):,} chars)")
    print()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    check_embed_model_compat(conn, EMBED_MODEL)

    total_chunks = 0
    skipped = 0

    for fpath, category, content in kb_files:
        chunks = chunk_text(content)
        print(f"Processing {os.path.basename(fpath)} → {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()

            # Skip if this exact content already exists
            existing = conn.execute(
                "SELECT id FROM chunks WHERE file_path = ? AND chunk_index = ? AND content_hash = ?",
                (fpath, i, content_hash),
            ).fetchone()

            if existing:
                skipped += 1
                continue

            # Remove old version of this chunk if content changed
            conn.execute(
                "DELETE FROM chunks WHERE file_path = ? AND chunk_index = ?",
                (fpath, i),
            )

            embedding = get_embedding(chunk)
            blob = embedding_to_blob(embedding)

            conn.execute(
                "INSERT INTO chunks (file_path, category, chunk_index, content, content_hash, embedding) VALUES (?, ?, ?, ?, ?, ?)",
                (fpath, category, i, chunk, content_hash, blob),
            )
            total_chunks += 1

        # Remove chunks beyond current count (file may have shrunk)
        conn.execute(
            "DELETE FROM chunks WHERE file_path = ? AND chunk_index >= ?",
            (fpath, len(chunks)),
        )
        conn.commit()

    print()
    print(f"Done! Embedded {total_chunks} new chunk(s), skipped {skipped} unchanged.")
    total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"Total chunks in DB: {total}")
    conn.close()


if __name__ == "__main__":
    main()
