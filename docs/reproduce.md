# Reproducing LogHetero

*Full reproduction recipes will land incrementally as each phase completes. This page documents what is reproducible right now.*

## Phase 0 — scaffold sanity (current)

```bash
git clone https://github.com/beiluomi/LogMLAGF.git
cd LogMLAGF
pip install --user uv
export PATH="$HOME/.local/bin:$PATH"
uv sync --extra dev
make lint test hello
```

Expected output: ruff clean, mypy clean, pytest green, `make hello` prints LogHetero version + Python version.

## Phase 1+ — TBD

Each subsequent phase will append a section here describing the exact commands, config files, expected metrics, and W&B run links required to reproduce its verification gate.
