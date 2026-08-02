.PHONY: dev test lint typecheck validate-schemas clean

dev:
	docker-compose up -d

dev-logs:
	docker-compose logs -f

dev-down:
	docker-compose down

install:
	pip install -e audit_v2[dev]

test:
	pytest --cov=audit_v2 --cov-report=term-missing -v

test-watch:
	pytest --cov=audit_v2 --cov-report=term-missing -v -f

lint:
	ruff check audit_v2/

typecheck:
	mypy --strict audit_v2/domain/

validate-schemas:
	python -m json.tool contracts/schemas/coverage.json /dev/null
	python -m json.tool contracts/schemas/provenance.json /dev/null
	python -m json.tool contracts/schemas/document.json /dev/null
	python -m json.tool contracts/schemas/finding.json /dev/null
	python -m json.tool contracts/schemas/check_catalog_entry.json /dev/null
	python -m json.tool contracts/schemas/check_catalog.json /dev/null

import-lint:
	@echo "Checking V2 does not import V1..."
	@! grep -r "from app\|import app" audit_v2/ --include="*.py" 2>/dev/null || (echo "FAIL: audit_v2 imports from app/" && exit 1)
	@echo "Checking V1 does not import V2..."
	@! grep -r "from audit_v2\|import audit_v2" app/ backend/ --include="*.py" 2>/dev/null || (echo "FAIL: V1 imports from audit_v2/" && exit 1)
	@echo "Import boundaries OK."

baseline-v1:
	python evaluation/measure_v1_baseline.py

generate-docs:
	python generate_test_bill.py --doc-type all --defects "line_item_error,gst_rate_error,grand_total_error,words_mismatch"

clean:
	rm -rf .pytest_cache .mypy_cache __pycache__
	rm -rf audit_v2/__pycache__ audit_v2/**/__pycache__
	rm -rf **/*.pyc

all: install validate-schemas lint typecheck import-lint test
