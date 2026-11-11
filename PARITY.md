# Baseline pins (0.2.0, Phase 0b, 2026-11-11)

- Version: `0.2.0` (first minor bump after 0.1.0; the Phase 0a re-sync ships here).
- Anima (verified in Phase 0a, 2026-11-10):
  - Base ref: `ab83c6cae1cde2f496a3dc4059cec20eafda22ae` (PR #12 merge)
  - Reflect-fix commit: `d3d13eaaf925daf535f0a31721700d93f3c5d609`
  - Pinned dependency: `anima>=0.1,<0.2` in `pyproject.toml`
    (declared as a direct dependency in Phase 0a; it was previously
    imported in ~30 files but only arrived transitively)
- Verified suites against this ref (Python 3.12, sibling-layout clones):
  anima 538 passed (100% coverage), magitech-harness 118/118 (100%),
  mth-plugins 260/260 (100%).
