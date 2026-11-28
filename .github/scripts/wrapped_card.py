"""Rebuild gitshine-wrapped.svg from live GitHub data.

Run by .github/workflows/wrapped-card.yml. Needs GITHUB_TOKEN in the environment.
Pass --data FILE to render from a saved JSON response instead of calling the API.
"""
import base64
import datetime as dt
import json
import os
import sys
import urllib.request
from collections import Counter

USER = "Kairo-2081"
OUT = "gitshine-wrapped.svg"
TZ = dt.timezone(dt.timedelta(hours=6))  # Asia/Dhaka

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    name
    avatarUrl(size: 96)
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
      commitContributionsByRepository(maxRepositories: 100) {
        contributions { totalCount }
        repository { primaryLanguage { name } }
      }
    }
  }
}
"""


def fetch(year, today):
    body = json.dumps({"query": QUERY, "variables": {
        "login": USER,
        "from": f"{year}-01-01T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z",
    }}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors"):
        sys.exit(f"GraphQL error: {data['errors']}")
    user = data["data"]["user"]
    with urllib.request.urlopen(user["avatarUrl"], timeout=30) as r:
        user["avatarData"] = f"data:{r.headers.get_content_type()};base64,{base64.b64encode(r.read()).decode()}"
    return user


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(user, year, today):
    cc = user["contributionsCollection"]
    counts = {}
    for w in cc["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            day = dt.date.fromisoformat(d["date"])
            if day.year == year:
                counts[day] = d["contributionCount"]

    total = sum(counts.values())

    # Current streak; a day with nothing yet doesn't break it until it's over.
    d = today if counts.get(today, 0) > 0 else today - dt.timedelta(days=1)
    streak = 0
    while counts.get(d, 0) > 0:
        streak += 1
        d -= dt.timedelta(days=1)

    langs = Counter()
    for r in cc["commitContributionsByRepository"]:
        lang = (r["repository"]["primaryLanguage"] or {}).get("name")
        if lang:
            langs[lang] += r["contributions"]["totalCount"]
    top_lang = langs.most_common(1)[0][0] if langs else "-"

    nz = sorted(v for v in counts.values() if v)
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)] if nz else [0, 0, 0]

    def level(v):
        if v <= 0:
            return 0
        return 1 if v <= q[0] else 2 if v <= q[1] else 3 if v <= q[2] else 4

    colors = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
    x0, y0, pitch, cell = 44, 266, 15.8, 12.6
    jan1 = dt.date(year, 1, 1)
    start = jan1 - dt.timedelta(days=(jan1.weekday() + 1) % 7)
    rects, day = [], jan1
    while day.year == year:
        col, row = (day - start).days // 7, (day.weekday() + 1) % 7
        c = colors[level(counts.get(day, 0))] if day <= today else colors[0]
        rects.append(f'<rect x="{x0 + col*pitch:.1f}" y="{y0 + row*pitch:.1f}" '
                     f'width="{cell}" height="{cell}" rx="2.5" fill="{c}"/>')
        day += dt.timedelta(days=1)

    name = esc(user.get("name") or USER)
    avatar = user["avatarData"]
    font = "Inter,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
    so_far = " so far" if today.year == year and today < dt.date(year, 12, 31) else ""
    grid = "\n".join(rects)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="956" height="505" viewBox="0 0 956 505" role="img" aria-label="{USER}'s {year} on GitHub: {total:,} contributions, {streak} day streak, top language {esc(top_lang)}">
<style>text{{font-family:{font}}}</style>
<defs><clipPath id="av"><circle cx="66" cy="72" r="23"/></clipPath></defs>
<rect width="956" height="505" rx="12" fill="#0d1117"/>
<circle cx="66" cy="72" r="25" fill="#3b82f6"/>
<image x="43" y="49" width="46" height="46" clip-path="url(#av)" xlink:href="{avatar}" href="{avatar}"/>
<text x="102" y="70" fill="#f0f6fc" font-size="20" font-weight="700">{name}</text>
<text x="102" y="90" fill="#8b949e" font-size="15">@{USER}</text>
<text x="906" y="78" fill="#8b949e" font-size="17" text-anchor="end">GitHub Wrapped {year}</text>
<text x="40" y="200" fill="#f0f6fc" font-size="80" font-weight="800" letter-spacing="-3">{total:,}</text>
<text x="44" y="234" fill="#8b949e" font-size="19">contributions in {year}{so_far}</text>
<text x="336" y="206" fill="#f0f6fc" font-size="28" font-weight="700">{streak}</text>
<text x="336" y="229" fill="#8b949e" font-size="15">day streak</text>
<text x="442" y="206" fill="#f0f6fc" font-size="28" font-weight="700">{esc(top_lang)}</text>
<text x="442" y="229" fill="#8b949e" font-size="15">top language</text>
{grid}
<text x="44" y="446" fill="#f0f6fc" font-size="20" font-weight="700">The Streak Keeper</text>
<text x="906" y="446" fill="#3fb950" font-size="17" text-anchor="end">gitshine.com/wrapped</text>
</svg>
''', total, streak, top_lang


def main():
    today = dt.datetime.now(TZ).date()
    year = today.year
    if "--data" in sys.argv:
        user = json.load(open(sys.argv[sys.argv.index("--data") + 1]))
        today = dt.date.fromisoformat(user.pop("today"))
        year = today.year
    else:
        user = fetch(year, today)
    svg, total, streak, lang = render(user, year, today)
    open(OUT, "w", encoding="utf-8").write(svg)
    print(f"{year}: {total} contributions, {streak} day streak, top language {lang}")


if __name__ == "__main__":
    main()
