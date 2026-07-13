help:	## Show all Makefile targets.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[33m%-30s\033[0m %s\n", $$1, $$2}'

format:	## Run code autoformatters (ruff, eslint --fix, prettier --write).
	pre-commit install
	git ls-files | xargs pre-commit run ruff-format --files
	git ls-files | xargs pre-commit run eslint --files

lint:	## Run linters: pre-commit (ruff, mypy, eslint, prettier)
	pre-commit install && git ls-files | xargs pre-commit run --show-diff-on-failure --files
