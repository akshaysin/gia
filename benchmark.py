#!/usr/bin/env python3
"""
Benchmark the DevOps RAG pipeline: embedding speed, retrieval speed, and chat generation (tokens/sec).
"""

import os
import sys
import time
import math
import json
import struct
import sqlite3
import requests

from config import DB_PATH, OLLAMA_URL, EMBED_MODEL, CHAT_MODEL, BENCH_MAX_TOKENS

BENCH_QUERIES = [
    "How do I check if a systemd service is running?",
    "Show me how to open a firewall port permanently",
    "How to view logs for a specific Kubernetes pod?",
    "What is the command to restart a Linux service?",
    "How do I debug a pod stuck in CrashLoopBackOff?",
]

SYSTEM_PROMPT = """\
You are a senior DevOps engineer assistant. Answer questions using ONLY the provided context.
Be concise, practical, and include relevant commands when appropriate."""


def get_embedding(text):
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def blob_to_embedding(blob):
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def search_chunks(conn, query_emb, top_k=3):
    rows = conn.execute("SELECT file_path, category, content, embedding FROM chunks").fetchall()
    scored = []
    for fp, cat, content, blob in rows:
        emb = blob_to_embedding(blob)
        sim = cosine_similarity(query_emb, emb)
        scored.append({"file": os.path.basename(fp), "category": cat, "content": content, "sim": sim})
    scored.sort(key=lambda x: x["sim"], reverse=True)
    return scored[:top_k]


def build_context(results):
    return "\n\n".join(
        f"--- {r['file']} ({r['category']}) ---\n{r['content']}" for r in results
    )


MAX_TOKENS = BENCH_MAX_TOKENS


def chat_generate(question, context):
    """Call Ollama chat API with streaming to measure TTFT and tok/s in real time."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": CHAT_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": MAX_TOKENS},
        },
        timeout=600,
        stream=True,
    )
    resp.raise_for_status()

    answer = ""
    t_first_token = None
    t_start = time.perf_counter()
    token_count = 0
    final_data = {}

    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        if chunk.get("message", {}).get("content"):
            token_count += 1
            if t_first_token is None:
                t_first_token = time.perf_counter() - t_start
            answer += chunk["message"]["content"]
            # Print progress dot every 20 tokens
            if token_count % 20 == 0:
                sys.stdout.write(".")
                sys.stdout.flush()
        if chunk.get("done"):
            final_data = chunk
            break

    t_total = time.perf_counter() - t_start

    return {
        "answer": answer,
        "token_count": token_count,
        "t_first_token": t_first_token or 0,
        "t_total_stream": t_total,
        "prompt_eval_count": final_data.get("prompt_eval_count", 0),
        "eval_count": final_data.get("eval_count", 0),
        "total_duration": final_data.get("total_duration", 0),
        "prompt_eval_duration": final_data.get("prompt_eval_duration", 0),
        "eval_duration": final_data.get("eval_duration", 0),
        "load_duration": final_data.get("load_duration", 0),
    }


def fmt_duration(sec):
    if sec < 1:
        return f"{sec * 1000:.1f}ms"
    return f"{sec:.2f}s"


def separator(title=""):
    if title:
        print(f"\n{'─' * 20} {title} {'─' * 20}")
    else:
        print("─" * 60)


def main():
    print("╔══════════════════════════════════════════════╗")
    print("║        RAG Pipeline Benchmark                ║")
    print("╠══════════════════════════════════════════════╣")
    print(f"║  Embed model: {EMBED_MODEL:<30s}║")
    print(f"║  Chat model:  {CHAT_MODEL:<30s}║")
    print(f"║  Queries:     {len(BENCH_QUERIES):<30d}║")
    print("╚══════════════════════════════════════════════╝")

    conn = sqlite3.connect(DB_PATH)
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"\nKnowledge DB: {chunk_count} chunks\n")

    # ── 1. Embedding benchmark ──────────────────────────────
    separator("1. EMBEDDING SPEED")
    embed_times = []
    for q in BENCH_QUERIES:
        t0 = time.perf_counter()
        emb = get_embedding(q)
        elapsed = time.perf_counter() - t0
        embed_times.append(elapsed)
        tokens_approx = len(q.split())
        print(f"  {fmt_duration(elapsed):>8s}  dim={len(emb)}  ~{tokens_approx} words  │ {q[:50]}")

    avg_embed = sum(embed_times) / len(embed_times)
    print(f"\n  Avg embedding time: {fmt_duration(avg_embed)}")
    print(f"  Min: {fmt_duration(min(embed_times))}  Max: {fmt_duration(max(embed_times))}")

    # ── 2. Retrieval benchmark ──────────────────────────────
    separator("2. RETRIEVAL SPEED (cosine search over all chunks)")
    retrieval_times = []
    for q in BENCH_QUERIES:
        q_emb = get_embedding(q)
        t0 = time.perf_counter()
        results = search_chunks(conn, q_emb)
        elapsed = time.perf_counter() - t0
        retrieval_times.append(elapsed)
        top_sim = results[0]["sim"] if results else 0
        print(f"  {fmt_duration(elapsed):>8s}  top_sim={top_sim:.3f}  │ {q[:50]}")

    avg_retrieval = sum(retrieval_times) / len(retrieval_times)
    print(f"\n  Avg retrieval time: {fmt_duration(avg_retrieval)}")
    print(f"  Min: {fmt_duration(min(retrieval_times))}  Max: {fmt_duration(max(retrieval_times))}")

    # ── 3. Generation benchmark ─────────────────────────────
    separator("3. GENERATION SPEED (full RAG: embed + retrieve + generate)")
    gen_stats = []

    for q in BENCH_QUERIES:
        # Full pipeline
        t_total_start = time.perf_counter()

        t0 = time.perf_counter()
        q_emb = get_embedding(q)
        t_embed = time.perf_counter() - t0

        t0 = time.perf_counter()
        results = search_chunks(conn, q_emb)
        t_retrieve = time.perf_counter() - t0

        context = build_context(results)

        t0 = time.perf_counter()
        resp = chat_generate(q, context)
        t_generate = time.perf_counter() - t0

        t_total = time.perf_counter() - t_total_start

        # Ollama returns timing in nanoseconds
        prompt_eval_count = resp["prompt_eval_count"]
        eval_count = resp["eval_count"]
        total_duration_ns = resp["total_duration"]
        prompt_eval_ns = resp["prompt_eval_duration"]
        eval_ns = resp["eval_duration"]
        load_ns = resp["load_duration"]

        # Tokens per second
        prompt_tps = (prompt_eval_count / (prompt_eval_ns / 1e9)) if prompt_eval_ns else 0
        gen_tps = (eval_count / (eval_ns / 1e9)) if eval_ns else 0

        stat = {
            "query": q,
            "t_embed": t_embed,
            "t_retrieve": t_retrieve,
            "t_generate": t_generate,
            "t_total": t_total,
            "ttft": resp["t_first_token"],
            "prompt_tokens": prompt_eval_count,
            "gen_tokens": eval_count,
            "prompt_tps": prompt_tps,
            "gen_tps": gen_tps,
            "model_load_ms": load_ns / 1e6,
            "prompt_eval_ms": prompt_eval_ns / 1e6,
            "gen_eval_ms": eval_ns / 1e6,
            "ollama_total_ms": total_duration_ns / 1e6,
            "answer_len": len(resp["answer"]),
        }
        gen_stats.append(stat)

        print(f"\n  Q: {q}")
        print(f"    Pipeline: embed={fmt_duration(t_embed)} → retrieve={fmt_duration(t_retrieve)} → generate={fmt_duration(t_generate)}")
        print(f"    Total wall time:   {fmt_duration(t_total)}")
        print(f"    TTFT:              {fmt_duration(resp['t_first_token'])}")
        print(f"    Prompt tokens:     {prompt_eval_count:>5d}  ({prompt_tps:>7.1f} tok/s)")
        print(f"    Generated tokens:  {eval_count:>5d}  ({gen_tps:>7.1f} tok/s)")
        print(f"    Model load:        {stat['model_load_ms']:.1f}ms")
        print(f"    Answer length:     {stat['answer_len']} chars")

    # ── 4. Summary ──────────────────────────────────────────
    separator("SUMMARY")

    avg_total = sum(s["t_total"] for s in gen_stats) / len(gen_stats)
    avg_prompt_tps = sum(s["prompt_tps"] for s in gen_stats) / len(gen_stats)
    avg_gen_tps = sum(s["gen_tps"] for s in gen_stats) / len(gen_stats)
    avg_prompt_tok = sum(s["prompt_tokens"] for s in gen_stats) / len(gen_stats)
    avg_gen_tok = sum(s["gen_tokens"] for s in gen_stats) / len(gen_stats)
    total_prompt_tok = sum(s["prompt_tokens"] for s in gen_stats)
    total_gen_tok = sum(s["gen_tokens"] for s in gen_stats)

    print(f"  Queries run:              {len(gen_stats)}")
    print(f"  Knowledge chunks:         {chunk_count}")
    print()
    print(f"  Avg embedding time:       {fmt_duration(avg_embed)}")
    print(f"  Avg retrieval time:       {fmt_duration(avg_retrieval)}")
    print(f"  Avg total pipeline time:  {fmt_duration(avg_total)}")
    print()
    print(f"  Prompt eval:    avg {avg_prompt_tps:>7.1f} tok/s  (avg {avg_prompt_tok:.0f} tokens)")
    print(f"  Generation:     avg {avg_gen_tps:>7.1f} tok/s  (avg {avg_gen_tok:.0f} tokens)")
    print()
    print(f"  Total tokens processed:   {total_prompt_tok} prompt + {total_gen_tok} generated = {total_prompt_tok + total_gen_tok}")
    print()

    # Time to first token
    avg_ttft = sum(s["ttft"] for s in gen_stats) / len(gen_stats)
    print(f"  Avg time-to-first-token:  {fmt_duration(avg_ttft)}")
    print()

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
