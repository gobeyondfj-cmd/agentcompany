# Contributing to Agent Company AI

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/gobeyondfj-cmd/agent-company-ai.git
   cd agent-company-ai
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   ```

3. **Install in development mode:**

   ```bash
   pip install -e ".[dev]"
   ```

   To also install blockchain/wallet support:

   ```bash
   pip install -e ".[dev,blockchain]"
   ```

## Running Tests

```bash
pytest tests/ -v
```

With coverage:

```bash
pytest tests/ -v --cov=agent_company_ai --cov-report=term-missing
```

## Code Style

- Python 3.10+ (use `from __future__ import annotations` for type hints)
- Use type hints on function signatures
- Follow existing code patterns and naming conventions
- Keep modules focused and imports explicit

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`
2. **Write tests** for any new functionality
3. **Run the test suite** to make sure nothing is broken
4. **Keep commits focused** — one logical change per commit
5. **Write a clear PR description** explaining what changed and why

## Reporting Bugs

Please use the [bug report template](https://github.com/gobeyondfj-cmd/agent-company-ai/issues/new?template=bug_report.md) when filing issues.

## Feature Requests

Please use the [feature request template](https://github.com/gobeyondfj-cmd/agent-company-ai/issues/new?template=feature_request.md).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
