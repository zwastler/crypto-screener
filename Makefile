format: ## Format code
	ruff format src

types:			## Run only types checks
	mypy src

check:			## Run checks (tests, style, types)
	make format
	make types

uv:			## Install uv (like pip tools).
	pip install -U uv

reqs: uv	## Create requirements.txt from requirements.in for all projects.
	rm -f requirements-dev.txt requirements.txt || true
	uv pip compile --generate-hashes requirements.in -o requirements.txt
	uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
	uv pip sync requirements-dev.txt

help:			## Show this help.
	@sed -ne '/@sed/!s/## //p' $(MAKEFILE_LIST)
