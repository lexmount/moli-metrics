# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Machine-generated **public** metrics and charts for the main project `lexmount/moli`. It exists so that moli's README (and website/blog) can hot-link static assets from `raw.githubusercontent.com/lexmount/moli-metrics/main/...` without polluting moli's commit history with metrics-update commits. Content here is written by scheduled GitHub Actions workflows, not by hand — humans (and Claude) edit the workflows/scripts; CI commits the data and charts.

## Layout

```
data/
  stars.json                    # historical star counts for lexmount/moli (fully machine-written)
assets/
  star-history.svg              # light-mode chart, hot-linked from moli's README
  star-history-dark.svg         # dark-mode variant (keep both in sync)
scripts/
  update_star_history.py        # stdlib-only Python; fetches data AND renders both SVGs
.github/workflows/
  update-star-history.yml       # hourly schedule + workflow_dispatch; commits only on change
```

`data/` and `assets/` are generated output — never hand-edit them; change the script and re-run. The script has two data modes: **timeline** (reconstructs full history from the stargazer timeline API; needs a privileged token) with fallback to **snapshot** (appends the current count as one point per run). Chart colors follow the dataviz reference palette; keep light/dark variants visually equivalent.

Future scope may add other **public** metrics: forks, contributors, release downloads, package registry downloads, benchmark trends.

## Design constraints (deliberate decisions — do not undo)

- **Hourly checks, but commits only on real change.** The owner asked for hourly freshness on 2026-08-21, replacing the original weekly cadence. Commit noise is held down by the script itself, not by the schedule: it compares the live star count against `data/stars.json` and returns without writing a single byte when they match. Preserve that early exit — regenerating unconditionally would rewrite the `updated` date and the SVG date caption at every UTC midnight and commit a date-only diff, which is exactly what the low-frequency schedule originally existed to prevent.
- **This repo must stay public.** Anonymous users must be able to load the raw SVGs from moli's README. Private/internal metrics (GitHub traffic, referral sources, conversion data) do NOT belong here — they would go in a separate private repo.
- **Token setup:** the workflow reads the `STAR_HISTORY_TOKEN` Actions secret — a fine-grained PAT or GitHub App token with read access to `lexmount/moli` stargazers. The default `GITHUB_TOKEN` belongs to moli-metrics and cannot read moli's stargazer timeline — GitHub restricted stargazer timeline access to repo admins/collaborators in July 2026, which is also why third-party services like star-history.com can no longer generate the chart and this repo exists. Without the secret the workflow still succeeds in snapshot mode.
- **Repo public, credentials private:** data, SVGs, workflows, and generation code are all public; tokens live only in Actions Secrets.

## Development notes

- There is no build system, linter, or test suite. To test the script locally:
  ```sh
  python3 scripts/update_star_history.py                                    # snapshot mode (no token)
  GH_TOKEN=$(gh auth token --user allen-lexmount) python3 scripts/update_star_history.py  # timeline mode
  ```
  The local `gh` CLI has two accounts; `allen-lexmount` has access to `lexmount/moli`, the active `chaobian` account does not. To visually check the SVGs: `qlmanage -t -s 1600 -o <outdir> assets/*.svg` and view the PNGs.
- Trigger the workflow manually with `gh workflow run update-star-history.yml`.
- The git remote uses the SSH host alias `lexmount.github.com` (identity-specific SSH config), not `github.com`. Commit author is the `lexmount` identity.
