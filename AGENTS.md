# Agent Guidelines & Engineering Standards

## 1. Core Architecture & Invariants

- **Zero Ancestral Mentions Rule**: Absolute prohibition against naming ancestral or upstream projects/brands anywhere in code, tests, docstrings, commits, or documentation.
- **Repository Role & Marketplace Structure**:
  - `mth-plugins` is the official extensible component marketplace for `magitech-harness`.
  - Implements pluggable model providers (`openrouter-provider`, `pollinations-provider`), domain tools (`bash-tool`, `codeact-tool`, `read-file-tool`, `write-file-tool`, `edit-file-tool`), and guardrails (`truncation-guard`, `compaction-guard`).
  - Every component ships with a `manifest.json` describing its metadata, type, and entrypoints, registered in `index.json`.
- **Capability Seam Symmetry**: Every component is a **Service Provider** mounted into `anima` context via an `apply(ctx)` entry point, registering capabilities onto explicit services (`ctx.llm`, `ctx.tools`, etc.).
- **Registrations are Effects**: Contributions register onto context and return an explicit disposer closure.
- **Fail-Loud Configuration**: Misconfiguration must fail loud at initialization rather than silently falling back or skipping missing referents.
- **No Hardcoded Tunables**: Provider endpoints, default models, and token pressure thresholds must be configurable parameters, not hidden hardcoded constants.

## 2. Pair Programming Principles

- **First Principles**: Question assumptions about the true nature of a problem rather than settling for reflexive patches.
- **Requirements First**: Verify requirements and contract invariants before implementing, especially when writing or modifying tests.
- **Research Before Guessing**: Search the codebase for existing patterns and protocols before introducing new abstractions.
- **Step-by-Step for Complex Refactoring**: Decompose large changes into verifiable checkpoints.
- **Direct Technical Honesty**: Concise, technical prose with zero fluff, cheerful filler, or emojis in code, commits, issues, and PRs.

## 3. What to Avoid

- **No Overwriting `.env`**: Never overwrite `.env` files without explicit user confirmation.
- **No Redundant Files**: Edit existing modules when sufficient rather than spawning duplicate files.
- **No Global Mutable State**: Keep library and service state encapsulated within context instances.
- **No Unnecessary Dependencies**: Leverage the standard library and existing dependencies; verify before adding packages with `uv add`.
- **No Reflexive / Internal Mocking in Tests**: Assert on observable behavior and contracts, not private attributes or internal mechanics.
- **No Silent Error Swallowing**: Empty `except` blocks must explicitly name the exception and document why it is safely ignored; keep `try` blocks narrow.

## 4. Python Conventions & Code Quality

- **Package Manager**: Use `uv` exclusively (`uv sync`, `uv run`, `uv add`). Never use raw `pip`. `uv.lock` is the single source of truth.
- **Python Style**: Adhere to the Google Python Style Guide. Format and lint with `ruff` (`line-length = 88`).
- **Strict Static Typing**: Every package enforces strict `mypy` (`disallow_untyped_defs = true`, `warn_return_any = true`, `warn_unused_configs = true`) and maintains a `py.typed` marker. Zero type errors allowed.
- **Filesystem Paths**: Use `pathlib.Path` for all filesystem operations; avoid raw string concatenation.
- **Import Hygiene**: Top-level imports only. No inline imports inside function bodies unless strictly required to break circular dependencies.
- **Boundary Validation**: Trust static typing across same-process internal boundaries. Enforce strict validation at JSON, file, CLI, process, and network wire boundaries.

## 5. Testing Discipline

- **Strict Test-Driven Development (TDD)**: Follow the Red ➔ Green ➔ Refactor cycle. Write failing unit tests before implementation.
- **100% Coverage Floor**: Every module must maintain 100% statement and branch coverage (`uv run pytest --cov-fail-under=100`).
- **Two Tiers Only**:
  - `tests/unit/`: Mirrors `src/` 1:1, flat naming, no `__init__.py` files.
  - `tests/integration/`: End-to-end integration across seams.
- **Hermetic Suites**: No external network access, real secrets, or wall-clock dependencies. Mock external seams at boundaries (`AsyncMock` for coroutines, `MagicMock` for synchronous callables).

## 6. Standard Commands

```sh
uv run pytest                          # Run test suite with 100% coverage gate
uv run ruff check src tests             # Lint codebase
uv run ruff format --check src tests    # Check formatting
uv run mypy src                         # Verify strict static type checking
```

## 7. Agent skills

### Issue tracker
GitHub Issues via `gh` CLI (`magitech-ai` organization). See `docs/agents/issue-tracker.md`.

### Triage labels
Canonical five-role triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs
Single-context layout (`CONTEXT.md` + `docs/adr/`). See `docs/agents/domain.md`.
