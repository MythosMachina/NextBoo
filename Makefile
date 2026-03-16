PYTHON ?= python3

.PHONY: check check-backend check-worker check-frontend check-tests release-readiness

check: check-backend check-worker check-frontend

check-backend:
	$(PYTHON) -m compileall backend/app

check-worker:
	$(PYTHON) -m compileall worker/app

check-frontend:
	cd frontend && npm run build
	cd frontend && npm run test:smoke

check-tests:
	PYTHONPATH=backend $(PYTHON) -m unittest discover -s backend/tests -p 'test_*.py'
	PYTHONPATH=worker $(PYTHON) -m unittest discover -s worker/tests -p 'test_*.py'
	cd frontend && npm run test:smoke
	$(PYTHON) scripts/check-index-coverage.py

release-readiness:
	./scripts/release-readiness.sh
