help:	## Show all Makefile targets.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[33m%-30s\033[0m %s\n", $$1, $$2}'

format:	## Run code autoformatters (ruff, eslint --fix, prettier --write).
	pre-commit install
	git ls-files | xargs pre-commit run ruff-format --files
	git ls-files | xargs pre-commit run eslint --files
	cd frontend && npm run format

lint:	## Run all linters (backend + frontend) via pre-commit.
	pre-commit install && git ls-files | xargs pre-commit run --show-diff-on-failure --files

lint-backend:	## Run backend linters directly (ruff, mypy) -- no pre-commit.
	ruff check .
	ruff format --check .
	mypy --config-file=mypy.ini --explicit-package-bases src

lint-frontend:	## Run frontend linters directly (eslint, prettier).
	cd frontend && npm run lint && npm run format:check

test:	## Run all tests (backend + frontend).
	$(MAKE) test-backend
	$(MAKE) test-frontend

test-backend:	## Run the backend test suite.
	pytest tests -v --capture=no

test-frontend:	## Run the frontend test suite.
	@echo "No frontend test suite configured yet."

coverage: # for ci purposes
	pytest --cov agent_inspector --cov-report=xml tests

coverage-report: ## Show coverage summary in terminal
	coverage report -m

coverage-html: ## Generate HTML coverage report
	coverage html
