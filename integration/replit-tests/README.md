# Replit-only verification

These checks inspect the Replit artifact manifests and are intentionally kept
outside `backend/tests`, so GitHub's general backend pytest job does not collect
tests that require the Replit workspace's `artifacts/` directory.

Run from the workspace root with:

```sh
HI_REPLIT_TEST_ROOT="$PWD" python -m pytest -q \
  .local/worktrees/horario-inteligente-fase4x2-pr-draft/integration/replit-tests
```

The test only reads artifact manifests. Build and startup checks for both the
flat GitHub tree and nested Replit tree run in
`scripts/smoke_production_startup_layouts.py` using temporary copies.
