COMPOSE     := $(shell command -v docker-compose 2>/dev/null || \
                 (docker compose version >/dev/null 2>&1 && echo "docker compose") || \
                 command -v podman-compose 2>/dev/null || \
                 echo "docker compose")
COMPOSE_GPU := $(COMPOSE) -f docker-compose.yml -f docker-compose.gpu.yml
IMAGE       := docker.io/akshaysin/gia

.DEFAULT_GOAL := help

# ── Help ───────────────────────────────────────────────────────────────────────
.PHONY: help
help:  ## Show this help
	@printf "\n  \033[1mgia — available targets\033[0m\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@printf "\n"

# ── End-user targets ───────────────────────────────────────────────────────────
.PHONY: chat
chat:  ## Start gia (CPU — works everywhere)
	$(COMPOSE) run --rm gia python3 chat.py

.PHONY: chat-gpu
chat-gpu:  ## Start gia with NVIDIA GPU acceleration
	$(COMPOSE_GPU) run --rm gia python3 chat.py

.PHONY: vectorize
vectorize:  ## Re-vectorize the knowledge base (after adding new docs)
	$(COMPOSE) run --rm gia python3 vectorize.py

.PHONY: bench
bench:  ## Run the RAG pipeline benchmark (CPU)
	$(COMPOSE) run --rm gia python3 benchmark.py

.PHONY: doctor
doctor:  ## Check connectivity, model config, and available resources
	$(COMPOSE) run --rm gia python3 doctor.py

.PHONY: bench-gpu
bench-gpu:  ## Run the RAG pipeline benchmark (GPU)
	$(COMPOSE_GPU) run --rm gia python3 benchmark.py

.PHONY: setup
setup:  ## Pull the latest pre-built image from Docker Hub
	$(COMPOSE) pull

.PHONY: down
down:  ## Stop and remove all containers (models volume is preserved)
	$(COMPOSE) down

# ── Maintainer targets ─────────────────────────────────────────────────────────
.PHONY: build
build:  ## Build image locally (maintainer)
	podman build -t $(IMAGE):latest .

.PHONY: push
push:  ## Build and push multi-arch image to Docker Hub (maintainer)
	podman build -t $(IMAGE):latest .
	podman push $(IMAGE):latest

.PHONY: release
release:  ## Tag and push a versioned release  e.g. make release VERSION=1.0.0
ifndef VERSION
	$(error VERSION is required — e.g. make release VERSION=1.0.0)
endif
	podman build -t $(IMAGE):$(VERSION) -t $(IMAGE):latest .
	podman push $(IMAGE):$(VERSION)
	podman push $(IMAGE):latest
