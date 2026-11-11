# Baseline pins (0.2.0, Phase 0b, 2026-11-11)

- Version: `0.2.0` (first minor bump after 0.1.0; the Phase 0a re-sync ships here).
- Anima (verified in Phase 0a, 2026-11-10):
  - Base ref: `1a9384345024d36711d948f96d217f5d43cb7e56` (PR #12 merge)
  - Reflect-fix commit: `898ac7d1f91308fb1290ce21e96537d48556e915`
  - Pinned dependency: `anima>=0.1,<0.2` in `pyproject.toml`
    (declared as a direct dependency in Phase 0a; it was previously
    imported in ~30 files but only arrived transitively)
- Verified suites against this ref (Python 3.12, sibling-layout clones):
  anima 538 passed (100% coverage), magitech-harness 118/118 (100%),
  mth-plugins 260/260 (100%).
