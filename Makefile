.PHONY: help install install-dev test test-verbose test-coverage test-quick clean lint format build build-binary test-install test-formula

help:
	@echo "repr CLI - Development Commands"
	@echo ""
	@echo "Installation:"
	@echo "  make install       Install package in editable mode"
	@echo "  make install-dev   Install with dev dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test          Run all tests"
	@echo "  make test-verbose  Run tests with verbose output"
	@echo "  make test-coverage Run tests with coverage report"
	@echo "  make test-quick    Run only passing tests (skip unimplemented)"
	@echo "  make test-install  Test curl installer script"
	@echo "  make test-formula  Test Homebrew formula"
	@echo ""
	@echo "Building:"
	@echo "  make build         Build Python package (wheel + sdist)"
	@echo "  make build-binary  Build standalone binary with PyInstaller"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          Run linters (ruff, mypy)"
	@echo "  make format        Format code (black, isort)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove test artifacts and cache"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pip install -r tests/requirements-dev.txt

test:
	pytest tests/

test-verbose:
	pytest -v tests/

test-coverage:
	pytest --cov=repr --cov-report=html --cov-report=term tests/
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

test-quick:
	pytest -v tests/ -k "not skip"

lint:
	ruff check repr tests
	mypy repr

format:
	black repr tests
	isort repr tests

clean:
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf **/__pycache__
	rm -rf **/*.pyc
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf build dist *.spec

build:
	python3 -m pip install --upgrade build
	python3 -m build

build-binary:
	python3 -m pip install pyinstaller
	pyinstaller repr.spec

test-install:
	@echo "Testing install script..."
	bash -n scripts/install.sh
	@echo "✓ Syntax check passed"
	@echo ""
	@echo "To test full installation:"
	@echo "  bash scripts/install.sh"

test-formula:
	@echo "Testing Homebrew formula..."
	@command -v brew >/dev/null 2>&1 || { echo "Homebrew not installed"; exit 1; }
	brew audit --new-formula Formula/repr.rb
	@echo "✓ Formula audit passed"
	@echo ""
	@echo "To test installation:"
	@echo "  brew install --build-from-source Formula/repr.rb"
	@echo "  brew test repr"
