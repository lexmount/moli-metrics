#!/usr/bin/env python3
"""Fetch star history for TARGET_REPO and regenerate data/stars.json + SVG charts.

Stdlib only — no dependencies to install on the CI runner.

Data strategy: try to reconstruct the full history from the stargazer timeline
(needs a token with admin/collaborator access to the target repo since GitHub's
July 2026 restriction). If that fails, fall back to appending a snapshot of the
current count, so the series still grows one point per run.
"""

import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_REPO = os.environ.get("TARGET_REPO", "lexmount/moli")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
DATA_PATH = REPO_ROOT / "data" / "stars.json"
ASSETS_DIR = REPO_ROOT / "assets"
MAX_TIMELINE_PAGES = 400  # 100 stargazers/page; the API stops listing past 40k anyway
MAX_SVG_POINTS = 500

# Colors from the validated reference palette (see dataviz skill, references/palette.md).
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "border": "rgba(11,11,11,0.10)",
        "ink": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "series": "#2a78d6",
    },
    "dark": {
        "surface": "#1a1a19",
        "border": "rgba(255,255,255,0.10)",
        "ink": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "series": "#3987e5",
    },
}


def gh_get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "moli-metrics",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_current_count():
    return gh_get(f"https://api.github.com/repos/{TARGET_REPO}")["stargazers_count"]


def fetch_timeline_samples(current_count, today):
    """Cumulative stars per day from the stargazer timeline. Raises on any failure."""
    starred_dates = []
    for page in range(1, MAX_TIMELINE_PAGES + 1):
        items = gh_get(
            f"https://api.github.com/repos/{TARGET_REPO}/stargazers?per_page=100&page={page}",
            accept="application/vnd.github.star+json",
        )
        for item in items:
            starred_dates.append(item["starred_at"][:10])
        if len(items) < 100:
            break
    if not starred_dates:
        raise ValueError("timeline returned no stargazers")
    starred_dates.sort()
    samples, count = [], 0
    for d in starred_dates:
        count += 1
        if samples and samples[-1]["date"] == d:
            samples[-1]["stars"] = count
        else:
            samples.append({"date": d, "stars": count})
    # The timeline omits unstars, so pin the final point to the true current count.
    if samples[-1]["date"] == today:
        samples[-1]["stars"] = current_count
    else:
        samples.append({"date": today, "stars": current_count})
    return samples


def snapshot_samples(stored, current_count, today):
    samples = stored["samples"] if stored else []
    if samples and samples[-1]["date"] == today:
        samples[-1]["stars"] = current_count
    else:
        samples.append({"date": today, "stars": current_count})
    return samples


def thin(samples):
    if len(samples) <= MAX_SVG_POINTS:
        return samples
    step = (len(samples) - 1) / (MAX_SVG_POINTS - 1)
    return [samples[round(i * step)] for i in range(MAX_SVG_POINTS)]


def nice_ticks(vmax):
    """Rounded tick step and axis top with headroom, 3-6 intervals."""
    target = max(vmax, 1) * 1.08
    for k in range(12):
        for m in (1, 2, 5):
            step = m * 10**k
            if target / step <= 5:
                return step, math.ceil(target / step) * step
    return 1, 1


def fmt_date(d, span_days):
    return d.strftime("%b %Y") if span_days > 300 else d.strftime("%b %-d")


def render_svg(samples, theme, updated):
    c = THEMES[theme]
    W, H = 800, 420
    x0, x1, y0, y1 = 64, W - 88, 76, H - 44

    pts = [(date.fromisoformat(s["date"]), s["stars"]) for s in samples]
    t_min, t_max = pts[0][0], pts[-1][0]
    if t_min == t_max:
        t_min = t_max - timedelta(days=7)
    span = (t_max - t_min).days
    step, v_top = nice_ticks(max(v for _, v in pts))

    def sx(t):
        return x0 + (t - t_min).days / span * (x1 - x0)

    def sy(v):
        return y1 - v / v_top * (y1 - y0)

    coords = [(sx(t), sy(v)) for t, v in pts]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(coords))
    area = f"{path} L{coords[-1][0]:.1f} {y1} L{coords[0][0]:.1f} {y1} Z"
    ex, ey = coords[-1]

    grid = "".join(
        f'<line x1="{x0}" y1="{sy(v)}" x2="{x1}" y2="{sy(v)}" stroke="{c["grid"]}" stroke-width="1"/>'
        f'<text x="{x0 - 10}" y="{sy(v) + 4}" text-anchor="end" fill="{c["muted"]}" '
        f'font-size="11" style="font-variant-numeric:tabular-nums">{v:,}</text>'
        for v in range(step, v_top + 1, step)
    )
    x_labels = "".join(
        f'<text x="{sx(t):.1f}" y="{y1 + 22}" text-anchor="middle" fill="{c["muted"]}" '
        f'font-size="11" style="font-variant-numeric:tabular-nums">{fmt_date(t, span)}</text>'
        for t in sorted({t_min + timedelta(days=round(span * f)) for f in (0, 1 / 3, 2 / 3, 1)})
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"
  font-family="system-ui, -apple-system, Segoe UI, sans-serif" role="img"
  aria-label="Star history of {TARGET_REPO}: {pts[-1][1]:,} stars as of {updated}">
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="8" fill="{c["surface"]}" stroke="{c["border"]}"/>
  <text x="24" y="36" fill="{c["ink"]}" font-size="18" font-weight="600">{TARGET_REPO}</text>
  <text x="24" y="57" fill="{c["secondary"]}" font-size="12.5">GitHub star history &#183; updated {updated}</text>
  {grid}
  <line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{c["axis"]}" stroke-width="1"/>
  {x_labels}
  <path d="{area}" fill="{c["series"]}" fill-opacity="0.1"/>
  <path d="{path}" fill="none" stroke="{c["series"]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="{c["series"]}" stroke="{c["surface"]}" stroke-width="2"/>
  <text x="{ex + 12:.1f}" y="{ey + 5:.1f}" fill="{c["ink"]}" font-size="14" font-weight="600">&#9733; {pts[-1][1]:,}</text>
</svg>
'''


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current = fetch_current_count()
    stored = json.loads(DATA_PATH.read_text()) if DATA_PATH.exists() else None

    # The star count is the only input that can change the output, so when it
    # matches what is already stored, write nothing at all. Runs are hourly:
    # regenerating would rewrite the "updated" date every UTC midnight and
    # commit a date-only diff. This also keeps the common case to one API call.
    if stored and stored["samples"] and stored["samples"][-1]["stars"] == current:
        print(f"{TARGET_REPO}: {current:,} stars — unchanged, nothing written")
        return

    try:
        samples, source = fetch_timeline_samples(current, today), "timeline"
    except (urllib.error.HTTPError, ValueError) as e:
        print(f"timeline unavailable ({e}); falling back to snapshot", file=sys.stderr)
        samples, source = snapshot_samples(stored, current, today), "snapshot"

    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(
            {"repo": TARGET_REPO, "updated": today, "source": source, "samples": samples},
            indent=2,
        )
        + "\n"
    )

    ASSETS_DIR.mkdir(exist_ok=True)
    svg_points = thin(samples)
    (ASSETS_DIR / "star-history.svg").write_text(render_svg(svg_points, "light", today))
    (ASSETS_DIR / "star-history-dark.svg").write_text(render_svg(svg_points, "dark", today))
    print(f"{TARGET_REPO}: {current:,} stars, {len(samples)} samples ({source})")


if __name__ == "__main__":
    main()
