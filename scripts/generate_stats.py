#!/usr/bin/env python3
"""Generate Tokyo Night themed GitHub stats cards for the profile README.

Reads live data from the GitHub GraphQL/REST APIs using GITHUB_TOKEN (the
default Actions token is enough for public data) and writes:

    dist/stats.svg   - overall statistics card
    dist/langs.svg   - most used languages card (by bytes, public non-fork repos)
    dist/stats.json  - the raw numbers behind both cards

Standard library only, so it runs anywhere Python 3.9+ is available.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import escape

LOGIN = os.environ.get("GH_USER", "Blueskale")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
OUT_DIR = os.environ.get("OUT_DIR", "dist")
HIDE_LANGS = {
    s.strip().lower()
    for s in os.environ.get(
        "HIDE_LANGS", "less,scss,makefile,ruby,puppet,powershell"
    ).split(",")
    if s.strip()
}
LANGS_COUNT = int(os.environ.get("LANGS_COUNT", "8"))
# Blend of byte share and repo-count share, as in github-readme-stats' size_weight/count_weight.
# 1.0/0.0 reproduces GitHub's raw byte percentages; 0.5/0.5 stops a single vendored blob dominating.
SIZE_WEIGHT = float(os.environ.get("SIZE_WEIGHT", "0.5"))
COUNT_WEIGHT = float(os.environ.get("COUNT_WEIGHT", "0.5"))

# Tokyo Night palette (matches the github-readme-stats "tokyonight" theme)
BG = "#1a1b27"
BORDER = "#2b2e44"
TITLE = "#70a5fd"
ICON = "#bf91f3"
TEXT = "#38bdae"
MUTED = "#a9b1d6"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"

if not TOKEN:
    sys.exit("GITHUB_TOKEN (or GH_TOKEN) is required")


def gh_request(url: str, data: dict | None = None, accept: str = "application/vnd.github+json"):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", accept)
    req.add_header("User-Agent", f"{LOGIN}-profile-stats")
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!, $after: String) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch() -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    year_ago = now - dt.timedelta(days=365)
    variables = {
        "login": LOGIN,
        "from": year_ago.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "after": None,
    }
    user = None
    repos: list[dict] = []
    while True:
        payload = gh_request("https://api.github.com/graphql", {"query": QUERY, "variables": variables})
        if "errors" in payload:
            sys.exit(f"GraphQL error: {payload['errors']}")
        u = payload["data"]["user"]
        if user is None:
            user = u
        repos.extend(u["repositories"]["nodes"])
        page = u["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        variables["after"] = page["endCursor"]

    # All-time commit count authored by the user (same approach as github-readme-stats)
    total_commits = None
    try:
        q = urllib.parse.quote(f"author:{LOGIN}")
        res = gh_request(f"https://api.github.com/search/commits?q={q}&per_page=1")
        total_commits = int(res.get("total_count", 0))
    except (urllib.error.URLError, ValueError, KeyError) as exc:  # fall back to last-12-months figure
        print(f"warning: commit search failed ({exc}); using last 12 months", file=sys.stderr)

    langs: dict[str, dict] = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name.lower() in HIDE_LANGS:
                continue
            entry = langs.setdefault(name, {"bytes": 0, "repos": 0, "color": edge["node"]["color"] or "#7aa2f7"})
            entry["bytes"] += edge["size"]
            entry["repos"] += 1
    for entry in langs.values():
        entry["size"] = (entry["bytes"] ** SIZE_WEIGHT) * (entry["repos"] ** COUNT_WEIGHT)

    return {
        "login": LOGIN,
        "name": user["name"] or LOGIN,
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "stars": sum(r["stargazerCount"] for r in repos),
        "public_repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "contributed_to": user["repositoriesContributedTo"]["totalCount"],
        "commits_last_year": user["contributionsCollection"]["totalCommitContributions"],
        "contributions_last_year": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "commits_total": total_commits,
        "languages": dict(sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)),
    }


# 16px Octicons (MIT, by GitHub)
ICONS = {
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Zm0 2.445L6.615 5.5a.75.75 0 0 1-.564.41l-3.097.45 2.24 2.184a.75.75 0 0 1 .216.664l-.528 3.084 2.769-1.456a.75.75 0 0 1 .698 0l2.77 1.456-.53-3.084a.75.75 0 0 1 .216-.664l2.24-2.183-3.096-.45a.75.75 0 0 1-.564-.41L8 2.694Z",
    "commits": "M1.643 3.143 .427 1.927A.25.25 0 0 0 0 2.104V5.75c0 .138.112.25.25.25h3.646a.25.25 0 0 0 .177-.427L2.715 4.215a6.5 6.5 0 1 1-1.18 4.458.75.75 0 1 0-1.493.154 8.001 8.001 0 1 0 1.6-5.684ZM7.75 4a.75.75 0 0 1 .75.75v2.992l2.028.812a.75.75 0 0 1-.557 1.392l-2.5-1A.751.751 0 0 1 7 8.25v-3.5A.75.75 0 0 1 7.75 4Z",
    "prs": "M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z",
    "issues": "M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z",
    "repo": "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z",
    "people": "M2 5.5a3.5 3.5 0 1 1 5.898 2.549 5.508 5.508 0 0 1 3.034 4.084.75.75 0 1 1-1.482.235 4 4 0 0 0-7.9 0 .75.75 0 0 1-1.482-.236A5.507 5.507 0 0 1 3.102 8.05 3.493 3.493 0 0 1 2 5.5ZM11 4a3.001 3.001 0 0 1 2.22 5.018 5.01 5.01 0 0 1 2.56 3.012.749.749 0 0 1-.885.954.752.752 0 0 1-.549-.514 3.507 3.507 0 0 0-2.522-2.372.75.75 0 0 1-.574-.73v-.352a.75.75 0 0 1 .416-.672A1.5 1.5 0 0 0 11 5.5.75.75 0 0 1 11 4Zm-5.5-.5a2 2 0 1 0-.001 3.999A2 2 0 0 0 5.5 3.5Z",
}


def fmt(n: int | None) -> str:
    if n is None:
        return "n/a"
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def stats_svg(d: dict) -> str:
    rows = [
        ("commits", "Total Commits" if d["commits_total"] is not None else "Commits (last 12 months)",
         d["commits_total"] if d["commits_total"] is not None else d["commits_last_year"]),
        ("repo", "Public Repositories", d["public_repos"]),
        ("issues", "Contributions (last 12 months)", d["contributions_last_year"]),
        ("people", "Followers", d["followers"]),
        ("star", "Total Stars Earned", d["stars"]),
        ("prs", "Total PRs", d["prs"]),
    ]
    width, row_h, top = 495, 25, 58
    height = top + row_h * len(rows) + 14
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" role="img" aria-labelledby="t">',
        f'<title id="t">{escape(d["name"])}\'s GitHub statistics</title>',
        "<style>",
        f".title{{font:600 18px {FONT};fill:{TITLE}}}",
        f".label{{font:400 14px {FONT};fill:{MUTED}}}",
        f".value{{font:600 14px {FONT};fill:{TEXT}}}",
        f".icon{{fill:{ICON}}}",
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="8" fill="{BG}" stroke="{BORDER}"/>',
        f'<text x="25" y="35" class="title">{escape(d["name"])}\'s GitHub Stats</text>',
    ]
    for i, (icon, label, value) in enumerate(rows):
        y = top + i * row_h
        out.append('<g class="row">')
        out.append(f'<svg x="25" y="{y}" width="16" height="16" viewBox="0 0 16 16"><path class="icon" d="{ICONS[icon]}"/></svg>')
        out.append(f'<text x="50" y="{y+13}" class="label">{escape(label)}:</text>')
        out.append(f'<text x="{width-25}" y="{y+13}" text-anchor="end" class="value">{fmt(value)}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def langs_svg(d: dict) -> str:
    items = list(d["languages"].items())[:LANGS_COUNT]
    total = sum(v["size"] for _, v in items) or 1
    items = [(n, v) for n, v in items if 100 * v["size"] / total >= 0.05]
    width, bar_w, bar_x = 350, 300, 25
    rows = (len(items) + 1) // 2
    height = max(222, 100 + rows * 28)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" role="img" aria-labelledby="t">',
        '<title id="t">Most used languages across public repositories</title>',
        "<style>",
        f".title{{font:600 18px {FONT};fill:{TITLE}}}",
        f".lang{{font:400 12px {FONT};fill:{MUTED}}}",
        f".pct{{font:600 12px {FONT};fill:{TEXT}}}",
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="8" fill="{BG}" stroke="{BORDER}"/>',
        '<text x="25" y="35" class="title">Most Used Languages</text>',
        f'<mask id="m"><rect x="{bar_x}" y="55" width="{bar_w}" height="8" rx="4" fill="#fff"/></mask>',
        '<g mask="url(#m)">',
    ]
    x = bar_x
    for name, v in items:
        w = bar_w * v["size"] / total
        out.append(f'<rect x="{x:.2f}" y="55" width="{w:.2f}" height="8" fill="{v["color"]}"/>')
        x += w
    out.append("</g>")
    for i, (name, v) in enumerate(items):
        col, row = i % 2, i // 2
        cx = bar_x + col * 160
        cy = 92 + row * 28
        pct = 100 * v["size"] / total
        out.append(f'<circle cx="{cx+5}" cy="{cy-4}" r="5" fill="{v["color"]}"/>')
        out.append(f'<text x="{cx+16}" y="{cy}" class="lang">{escape(name)} <tspan class="pct">{pct:.1f}%</tspan></text>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    data = fetch()
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg(data))
    with open(os.path.join(OUT_DIR, "langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg(data))
    with open(os.path.join(OUT_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    summary = {k: v for k, v in data.items() if k != "languages"}
    total = sum(x["size"] for x in data["languages"].values()) or 1
    summary["languages"] = {k: round(100 * v["size"] / total, 1) for k, v in list(data["languages"].items())[:LANGS_COUNT]}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
