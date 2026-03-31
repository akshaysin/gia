# gia

A local, privacy-first AI assistant for DevOps and security engineers. Answers questions about Kubernetes, Docker, Ansible, Terraform, Linux, MITRE ATT&CK, Sigma, YARA, NIST, and more — powered by a curated knowledge base that runs entirely on your machine via [Ollama](https://ollama.com).

No data leaves your machine. No API keys needed.

## Quick Start

You need **Docker** (or **Podman**) with Compose support — nothing else.

```bash
git clone https://github.com/akshaysin/gia.git
cd gia
docker compose run --rm gia        # or: podman-compose run --rm gia
```

First run pulls ~3 GB of models automatically. Subsequent starts are instant.

## Commands

### Make targets

| Target | Description |
|---|---|
| `make chat` | Start gia (CPU) |
| `make chat-gpu` | Start gia with NVIDIA GPU acceleration |
| `make vectorize` | Re-index the knowledge base after adding docs |
| `make bench` | Performance benchmark |
| `make down` | Stop all containers |

### In-chat commands

| Command | Description |
|---|---|
| `help` | Show available commands |
| `sources` | Knowledge sources cited in the last answer |
| `history` | Conversation history |
| `clear` | Reset conversation |
| `quit` | Exit |

## Adding Knowledge

Drop `.md` or `.pdf` files into `knowledge/` (use subdirectories by topic), then re-index:

```bash
make vectorize
```

## GPU Acceleration

GPU mode requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on the host.

```bash
# Install (Fedora/RHEL)
sudo dnf install -y nvidia-container-toolkit

# Podman only — generate CDI spec once
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

# Run with GPU
make chat-gpu
```

## Configuration

Override settings via environment variables in `docker-compose.yml` → `gia.environment`:

| Variable | Default | Description |
|---|---|---|
| `CHAT_MODEL` | `auto` | Chat model — `auto` selects based on available VRAM (see below) |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `EMBED_DIM` | `0` | Embedding dimensions (`0` = full 768; set `256` or `384` for lower memory) |
| `TOP_K` | `5` | Knowledge chunks per query |
| `SIM_THRESHOLD` | `0.3` | Minimum cosine similarity |
| `HISTORY_TURNS` | `8` | Conversation turns kept in context |
| `CODE_STYLE` | `monokai` | Syntax highlight theme |

Example — use a specific model:

```yaml
environment:
  CHAT_MODEL: qwen2.5-coder:7b
```

### Auto Model Selection

When `CHAT_MODEL=auto` (the default), gia detects your GPU VRAM via `nvidia-smi` and picks the best model:

| VRAM | Model | Size |
|---|---|---|
| ≥ 8 GB | `qwen2.5-coder:7b` | Large |
| ≥ 3.5 GB | `phi4-mini:3.8b` | Default |
| < 3.5 GB / CPU only | `qwen2.5:1.5b` | Tiny |

Set `CHAT_MODEL` explicitly to override.

### Matryoshka Embedding Dimensions

The default embedding dimension is 768. If you're running on constrained hardware or scaling to a large knowledge base, you can reduce it:

```yaml
environment:
  EMBED_DIM: 256    # 3× less memory, ~5% quality trade-off
```

> **Note:** Changing `EMBED_DIM` requires re-vectorizing: `make vectorize`

## Architecture

```
docker-compose.yml
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ollama (model server)  ◄──────►  gia (chat + RAG)          │
│  ├─ phi4-mini:3.8b (auto)            ├─ chat.py             │
│  └─ nomic-embed-text                 ├─ vectorize.py        │
│                                      ├─ knowledge.db        │
│                                      └─ VectorIndex (numpy) │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

1. Your question is embedded into a vector via `nomic-embed-text`
2. Numpy vectorized cosine similarity finds the top-K relevant chunks from an in-memory index
3. Matched context is passed to the auto-selected chat model for answer generation
4. Response streams live with full markdown and syntax highlighting

### Performance

All embeddings are loaded into a numpy matrix at startup. Search uses a single BLAS matrix-vector multiply instead of per-row Python loops. Repeated queries hit an LRU cache and skip the embedding API entirely.

| Metric | Before | After |
|---|---|---|
| Retrieval | 278 ms | **0.5 ms** (556× faster) |
| Embedding (cached) | 298 ms | **0 ms** |
| Pipeline (end-to-end) | 8.9 s | **6.5 s** (28% faster) |

## Without Make

```bash
# Docker
docker compose run --rm gia                         # chat
docker compose run --rm gia python3 vectorize.py    # re-index
docker compose run --rm gia python3 benchmark.py    # benchmark

# Docker — GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia

# Podman
podman-compose run --rm gia
podman-compose run --rm gia python3 vectorize.py

# Podman — GPU (requires CDI spec)
podman-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia
```

---

<details>
<summary><strong>Maintainer Reference</strong></summary>

### CI/CD

Every push to `main` triggers `.github/workflows/publish.yml` — builds `linux/amd64` + `linux/arm64` and pushes to Docker Hub.

Required GitHub secrets: `DOCKER_USERNAME`, `DOCKER_TOKEN`.

### Manual release

```bash
make release VERSION=1.2.0
```

### Rebuild image with updated knowledge

```bash
make vectorize   # re-index knowledge.db
make push        # build & push to Docker Hub
```

</details>

## License

MIT
