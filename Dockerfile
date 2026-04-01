# ══════════════════════════════════════════════════════════════════════════════
# Stage 1 — builder
#   Installs Python packages into an isolated /install prefix.
#   pip, wheel caches, and any build-time artefacts stay here and are
#   never copied to the runtime image.
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt requirements-vectorize.txt ./

# Install all deps (including PyMuPDF) in builder — needed for vectorize step
RUN pip install --no-cache-dir --prefix=/install -r requirements-vectorize.txt


# ══════════════════════════════════════════════════════════════════════════════
# Stage 2 — runtime
#   Lean final image: only the compiled site-packages + app code.
#   No pip, no build cache, no leftover metadata.
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="gia"
LABEL org.opencontainers.image.description="DevOps & Endpoint Security AI agent — RAG-powered CLI using Ollama"
LABEL org.opencontainers.image.source="https://github.com/akshaysin/gia"
LABEL org.opencontainers.image.licenses="MIT"

# Copy only the installed packages from the builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

# ── Application code ───────────────────────────────────────────────────────────
COPY *.py ./

# ── Knowledge base (SQLite + markdown sources; PDFs excluded via .dockerignore) ─
COPY knowledge.db .
COPY knowledge/ ./knowledge/

# ── Entrypoint ─────────────────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "chat.py"]
