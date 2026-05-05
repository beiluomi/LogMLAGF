.PHONY: help hello lint format test sync sync-ml prepare-data pretrain finetune-anomaly ablation cross-dataset anonymize clean

UV := uv
PY := $(UV) run python

help:
	@echo "LogHetero — make targets"
	@echo "  make sync             - Install dev environment (uv sync --extra dev)"
	@echo "  make sync-ml          - Install ML stack on top of dev (uv sync --extra dev --extra ml)"
	@echo "  make hello            - Smoke check: print version + GPU availability"
	@echo "  make lint             - Run ruff + mypy"
	@echo "  make format           - Auto-format with ruff"
	@echo "  make test             - Run pytest"
	@echo "  --- Phase-gated targets (placeholders until each phase lands) ---"
	@echo "  make prepare-data     - Phase 1: build data pipeline"
	@echo "  make pretrain         - Phase 7: joint HTGN-LM + RAPA-GTCL pretraining"
	@echo "  make finetune-anomaly - Phase 8: anomaly-detection fine-tuning"
	@echo "  make cross-dataset    - Phase 9: DARPA TC E3 cross-dataset eval"
	@echo "  make ablation         - Phase 11: ablation matrix B0-B6"
	@echo "  make anonymize        - Phase 12: double-blind submission anonymization"
	@echo "  make clean            - Remove caches and outputs"

sync:
	$(UV) sync --extra dev

sync-ml:
	$(UV) sync --extra dev --extra ml

hello:
	$(PY) -m loghetero.cli hello

lint:
	$(UV) run ruff check src tests
	$(UV) run mypy src

format:
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

test:
	$(UV) run pytest tests

# --- Phase-gated targets ---

prepare-data:
	@echo "[Phase 1+] not yet implemented; see plan/Phase-1." && exit 1

pretrain:
	@echo "[Phase 7+] not yet implemented; see plan/Phase-7." && exit 1

finetune-anomaly:
	@echo "[Phase 8+] not yet implemented; see plan/Phase-8." && exit 1

cross-dataset:
	@echo "[Phase 9+] not yet implemented; see plan/Phase-9." && exit 1

ablation:
	@echo "[Phase 11+] not yet implemented; see plan/Phase-11." && exit 1

anonymize:
	@echo "[Phase 12] anonymization deferred to pre-submission." \
	  "See docs/design_decisions.md decision 3."
	@echo "Will be implemented as scripts/anonymize_repo.sh + scripts/anonymize_check.sh."

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage outputs/ multirun/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
