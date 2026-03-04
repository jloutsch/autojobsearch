# Contributing to AutoJobSearch

Thanks for your interest in contributing! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork and create a branch:
   ```bash
   git clone https://github.com/YOUR_USERNAME/autojobsearch.git
   cd autojobsearch
   git checkout -b feature/your-feature
   ```
3. Set up the development environment:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Adding a New Job Source

The most common contribution is adding a new job board source. Each source lives in `sources/` and extends `BaseSource`:

1. Create `sources/yoursite.py` implementing `collect()` that returns `list[JobListing]`
2. Add test file `tests/test_sources/test_yoursite.py` with mocked HTTP responses
3. Add test fixtures in `tests/fixtures/`
4. Register the source in `main.py`
5. Update `CLAUDE.md` with the new source details

See existing sources like `sources/remotive.py` (simple JSON API) or `sources/ashby.py` (per-company boards) for examples.

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

All tests must pass before submitting a PR. Tests use the `responses` library to mock HTTP calls — no network access needed.

## Code Style

- Keep changes focused and minimal
- Follow existing patterns in the codebase
- Use `logging` module, not `print()`
- Handle errors gracefully — one source failure should never crash the pipeline

## Pull Requests

- Create feature branches from `main`
- Write a clear description of what your change does and why
- Include tests for new functionality
- Keep PRs focused on a single change

## Reporting Issues

Use the GitHub issue templates for bug reports and feature requests. Include enough detail to reproduce bugs (Python version, OS, error output).
