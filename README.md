# gia — DevOps & Endpoint Security AI Agent

**gia** is a local, privacy-first AI assistant for DevOps engineers and security practitioners. It answers questions about Kubernetes, Linux, Docker, Ansible, Terraform, MITRE ATT&CK, Sigma rules, YARA, NIST frameworks, and more — all from a curated knowledge base stored on your machine.

No data leaves your machine. Everything runs locally via [Ollama](https://ollama.com).

---

## Prerequisites

You need a container runtime with Compose support. Pick whichever you already have (or prefer):

| Runtime | Platform | Install guide |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Mac / Windows / Linux | Easiest option — Compose included |
| [Docker Engine + Compose plugin](https://docs.docker.com/engine/install/) | Linux | Lightweight server install |
| [Podman Desktop](https://podman-desktop.io/) | Mac / Windows / Linux | Rootless, daemonless alternative |
| [Podman + podman-compose](https://podman.io/docs/installation) | Linux | `sudo dnf install podman podman-compose` or `brew install podman` |

That's it. No Python, no Ollama, no model downloads required up front — the agent handles everything on first start.

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/akshaysin/gia.git
cd gia

# 2. Start the agent  (first run downloads ~3 GB of models — subsequent starts are instant)
docker compose run --rm gia      # Docker
podman-compose run --rm gia      # Podman

# — or, if you have Make installed —
make chat
```

> **Podman Desktop users (Mac/Windows):** make sure the Podman machine is started
> (`podman machine start`) before running any commands.

On first run gia will:
1. Start the Ollama model server automatically
2. Pull the `nomic-embed-text` embedding model (~274 MB)
3. Pull the `phi4-mini:3.8b` chat model (~2.5 GB)
4. Drop you into the interactive chat

---

## Usage

| Command | What it does |
|---|---|
| `make chat` | Start gia — CPU mode, works on any machine |
| `make chat-gpu` | Start gia with NVIDIA GPU acceleration |
| `make vectorize` | Re-index the knowledge base (run after adding new docs) |
| `make bench` | Run a performance benchmark — CPU |
| `make bench-gpu` | Run a performance benchmark — GPU |
| `make setup` | Pull the latest pre-built image from Docker Hub |
| `make down` | Stop all containers (your model cache is preserved) |

Without Make:

```bash
# CPU (works everywhere)
docker compose run --rm gia                         # chat
docker compose run --rm gia python3 vectorize.py    # re-index
docker compose run --rm gia python3 benchmark.py    # benchmark

# GPU (NVIDIA — requires nvidia-container-toolkit on the host)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia

# Podman — CPU
podman-compose run --rm gia
podman-compose run --rm gia python3 vectorize.py
podman-compose run --rm gia python3 benchmark.py

# Podman — GPU (CDI spec must be generated first: sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml)
podman-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia python3 chat.py
podman-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm gia python3 benchmark.py
```

### Chat commands

Once inside the REPL:

| Input | Action |
|---|---|
| `help` | Show available commands |
| `history` | Print conversation history |
| `sources` | Show sources used in the last answer |
| `clear` | Clear the conversation |
| `quit` / `exit` | Exit |

---

## Configuration

All settings are controlled by environment variables. Override them in `docker-compose.yml` under the `gia → environment` section:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://ollama:11434` | Ollama API base URL |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model name |
| `CHAT_MODEL` | `phi4-mini:3.8b` | Chat model name |
| `TOP_K` | `5` | Number of knowledge chunks retrieved per query |
| `SIMILARITY_THRESHOLD` | `0.3` | Minimum cosine similarity to include a chunk |
| `HISTORY_TURNS` | `8` | Conversation turns kept in context |
| `WRAP_WIDTH` | `90` | Terminal output wrap width (characters) |
| `CODE_STYLE` | `monokai` | Pygments syntax highlight theme (`dracula`, `native`, `one-dark`, …) |
| `BENCH_MAX_TOKENS` | `100` | Max tokens generated per query in benchmark mode |

**Example** — swap in a larger model:

```yaml
# docker-compose.yml
environment:
  CHAT_MODEL: qwen2.5-coder:7b
```

### GPU acceleration (NVIDIA)

By default gia runs in **CPU mode** and works on any machine — no GPU required.

To enable GPU acceleration, use the `docker-compose.gpu.yml` override (or `make chat-gpu`). This requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on the host.

**Linux (Docker or Podman):**
```bash
# Install nvidia-container-toolkit (Fedora/RHEL)
sudo dnf install -y nvidia-container-toolkit
# Generate CDI spec (needed once, Podman only)
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
# Restart your container daemon
sudo systemctl restart docker    # or: sudo systemctl restart podman
```

**Ubuntu/Debian:**
```bash
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
sudo systemctl restart docker
```

---

## Adding Custom Knowledge

1. Drop `.md` or `.pdf` files into the `knowledge/` folder (create subdirectories by topic)
2. Re-index:

```bash
make vectorize
# Docker:  docker compose run --rm gia python3 vectorize.py
# Podman:  podman-compose run --rm gia python3 vectorize.py
```

3. Rebuild the image so the updated `knowledge.db` is baked in:

```bash
make push   # maintainers
# Docker:  docker compose build && docker compose push
# Podman:  podman-compose build && podman push akshaysin/gia:latest
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  docker-compose.yml                                     │
│                                                         │
│  ┌──────────────┐        ┌────────────────────────────┐ │
│  │  ollama      │◄──────►│  gia                       │ │
│  │  (model srv) │        │  chat.py     — REPL        │ │
│  │              │        │  vectorize.py — ingest     │ │
│  │  phi4-mini   │        │  benchmark.py — perf       │ │
│  │  nomic-embed │        │  knowledge.db — SQLite RAG │ │
│  └──────────────┘        └────────────────────────────┘ │
│        ▲                                                 │
│  gia_ollama_models (Docker volume — survives restarts)  │
└─────────────────────────────────────────────────────────┘
```

**RAG pipeline:**

1. User question → `nomic-embed-text` → 768-dim query vector
2. Cosine similarity search over 2,517 pre-indexed chunks in `knowledge.db`
3. Top-K chunks passed as context to `phi4-mini:3.8b`
4. Streamed answer rendered with full syntax highlighting

---

## Maintainer Reference

### One-time setup

```bash
# Docker — create a buildx builder for multi-arch output
docker buildx create --use --name gia-builder

# Podman — multi-arch builds via buildah (included with podman)
podman manifest create akshaysin/gia:latest
```

Add two secrets in your GitHub repo (**Settings → Secrets and variables → Actions**):

| Secret | Value |
|---|---|
| `DOCKER_USERNAME` | Your Docker Hub username (`akshaysin`) |
| `DOCKER_TOKEN` | A Docker Hub access token (read/write) |

### CI/CD

Every push to `main` triggers `.github/workflows/publish.yml`, which:
- Builds for `linux/amd64` and `linux/arm64`
- Pushes `akshaysin/gia:latest` and `akshaysin/gia:sha-<commit>` to Docker Hub
- Uses GitHub Actions cache to speed up subsequent builds

### Manual release

```bash
make release VERSION=1.2.0
```

---

## License

MIT
