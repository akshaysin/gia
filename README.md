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

First run pulls the required Ollama models automatically. Subsequent starts reuse the persisted model cache.

## CPU-Only Quick Start

For most macOS and Windows users, the default path is the right one:

```bash
git clone https://github.com/akshaysin/gia.git
cd gia
docker compose run --rm gia
```

What to expect on first launch:

- `gia` starts in a CPU-friendly profile by default
- the app waits for Ollama, pulls any missing models, then opens the chat UI
- first startup may take a few minutes depending on network speed and machine performance
- later launches reuse the model cache stored in the `gia_ollama_models` volume

If you're using Docker Desktop on macOS or Windows, give the Docker VM at least **8 GB RAM** if possible. CPU-only inference works below that, but response times can degrade noticeably.

## Commands

### Make targets

| Target | Description |
|---|---|
| `make chat` | Start gia (CPU) |
| `make chat-gpu` | Start gia with NVIDIA GPU acceleration |
| `make vectorize` | Re-index the knowledge base after adding docs |
| `make bench` | Performance benchmark |
| `make bench-gpu` | Performance benchmark with the GPU override |
| `make doctor` | Check model config, Ollama connectivity, and visible resources |
| `make setup` | Pull the latest published image |
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

Runtime defaults come from `config.py`, and the compose files can override them via `gia.environment`.

| Variable | Default | Description |
|---|---|---|
| `GIA_PROFILE` | unset in `config.py`, `compat` in `docker-compose.yml`, `balanced` in `docker-compose.gpu.yml` | Friendly model preset |
| `CHAT_MODEL` | `auto` in local Python runs, `qwen2.5:1.5b` in `docker-compose.yml`, `phi4-mini:3.8b` in `docker-compose.gpu.yml` | Chat model |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `EMBED_DIM` | `0` | Embedding dimensions (`0` = full 768; set `256` or `384` for lower memory) |
| `TOP_K` | `5` | Knowledge chunks per query |
| `SIMILARITY_THRESHOLD` | `0.3` | Minimum cosine similarity |
| `HISTORY_TURNS` | `8` | Conversation turns kept in context |
| `WRAP_WIDTH` | `90` | Terminal wrapping width used by the chat UI |
| `CODE_STYLE` | `monokai` | Syntax highlight theme |
| `BENCH_MAX_TOKENS` | `100` | Max generated tokens per benchmark query |

Example — use a specific model:

```yaml
environment:
  CHAT_MODEL: qwen2.5-coder:7b
```

### Model Selection

`gia` supports a user-friendly profile setting as well as direct model overrides.

| Profile | Model | Intended use |
|---|---|---|
| `compat` | `qwen2.5:1.5b` | safest CPU-first choice for broad compatibility |
| `balanced` | `phi4-mini:3.8b` | better quality on stronger CPUs or 4 GB-class NVIDIA GPUs |
| `quality` | `qwen2.5-coder:7b` | highest quality, expects substantially more resources |

Compose defaults are explicit so model choice does not depend on cross-container GPU detection:

| Launch mode | Model | Why |
|---|---|---|
| `docker compose run --rm gia` | `GIA_PROFILE=compat` → `qwen2.5:1.5b` | safe CPU-first default for broad compatibility |
| `make chat-gpu` / GPU compose override | `GIA_PROFILE=balanced` → `phi4-mini:3.8b` | better quality on 4 GB-class NVIDIA GPUs |
| direct local Python run with `CHAT_MODEL=auto` | auto-selected tier | Uses runtime detection from `pull_models.py` |

`CHAT_MODEL` always overrides `GIA_PROFILE` when you want full control.

Example — switch to the balanced profile:

```yaml
environment:
  GIA_PROFILE: balanced
```

`CHAT_MODEL=auto` is still supported in local non-container runs and falls back to runtime hardware detection, but compose files now use explicit profiles.

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
│  ├─ qwen2.5:1.5b / phi4-mini:3.8b    ├─ chat.py             │
│  └─ nomic-embed-text                 ├─ vectorize.py        │
│                                      ├─ knowledge.db        │
│                                      └─ VectorIndex (numpy) │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

1. Your question is embedded into a vector via `nomic-embed-text`
2. Numpy vectorized cosine similarity finds the top-K relevant chunks from an in-memory index
3. Matched context is passed to the configured chat model for answer generation
4. Response streams live with full markdown and syntax highlighting

### Performance

All embeddings are loaded into a numpy matrix at startup. Search uses a single BLAS matrix-vector multiply instead of per-row Python loops. Repeated queries hit an LRU cache and skip the embedding API entirely.

| Metric | Before | After |
|---|---|---|
| Retrieval | 278 ms | **0.5 ms** (556× faster) |
| Embedding (cached) | 298 ms | **0 ms** |
| Pipeline (end-to-end) | 8.9 s | **6.5 s** (28% faster) |

## Platform Support

| Platform | Status | Notes |
|---|---|---|
| macOS Apple Silicon | Recommended | best non-NVIDIA path; use Docker Desktop and the default CPU profile |
| macOS Intel | Supported | works, but CPU-only response times vary more by hardware |
| Windows + Docker Desktop | Supported | CPU-only is the default; allocate more Docker VM memory if responses feel slow |
| Linux without NVIDIA | Supported | default CPU profile works well for general compatibility |
| Linux with NVIDIA | Best performance | use `make chat-gpu` or the GPU compose override |

## Troubleshooting

Run the built-in diagnostic command to verify Ollama connectivity, model selection, and visible resources:

```bash
make doctor
```

This is especially useful on macOS and Windows, where Docker Desktop VM memory settings can strongly affect CPU-only performance.

## Without Make

```bash
# Docker
docker compose run --rm gia                         # chat
docker compose run --rm gia python3 vectorize.py    # re-index
docker compose run --rm gia python3 benchmark.py    # benchmark
docker compose run --rm gia python3 doctor.py       # diagnostics
docker compose pull                                 # pull latest image

# Docker — GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia                  # chat
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia python3 benchmark.py  # benchmark

# Podman
podman-compose run --rm gia
podman-compose run --rm gia python3 vectorize.py
podman-compose run --rm gia python3 benchmark.py
podman-compose run --rm gia python3 doctor.py
podman-compose pull

# Podman — GPU (requires CDI spec)
podman-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia                  # chat
podman-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia python3 benchmark.py  # benchmark
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
