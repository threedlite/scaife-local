# GitHub Actions

This local fork does not use the upstream Perseus deployment workflows
(which push images to Heroku + Google Cloud with secrets we don't have).
They are preserved for reference at `.github/workflows-upstream-disabled/`
but GitHub only auto-runs files under `workflows/`, so nothing runs
from a stock clone.

If you fork Perseus's deployment pipeline, rename the directory back to
`workflows/` and populate the required secrets in your repo settings.
