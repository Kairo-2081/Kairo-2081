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
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont

USER = "Kairo-2081"
OUT = "gitshine-wrapped.svg"
TZ = dt.timezone(dt.timedelta(hours=6))  # Asia/Dhaka
FONTS = Path(__file__).resolve().parent.parent / "fonts"  # Geist, SIL OFL (see fonts/OFL.txt)
W, H, PAD = 956, 445, 44


@lru_cache(None)
def _font(name):
    return TTFont(FONTS / f"{name}.woff2")


@lru_cache(None)
def font_b64(name):
    return base64.b64encode((FONTS / f"{name}.woff2").read_bytes()).decode()


def measure(text, name, size, tracking=0.0):
    f = _font(name)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    adv = sum(hmtx[cmap.get(ord(ch), cmap[ord("?")])][0] for ch in text)
    return adv * size / upm + tracking * max(len(text) - 1, 0)

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
    pitch = (W - 2 * PAD + 3) / 53
    cell = pitch - 3
    x0, y0 = PAD, 282
    jan1 = dt.date(year, 1, 1)
    start = jan1 - dt.timedelta(days=(jan1.weekday() + 1) % 7)
    rects, day = [], jan1
    while day.year == year:
        col, row = (day - start).days // 7, (day.weekday() + 1) % 7
        c = colors[level(counts.get(day, 0))] if day <= today else colors[0]
        rects.append(f'<rect x="{x0 + col*pitch:.1f}" y="{y0 + row*pitch:.1f}" '
                     f'width="{cell}" height="{cell}" rx="3" fill="{c}"/>')
        day += dt.timedelta(days=1)

    name = esc(user.get("name") or USER)
    avatar = user["avatarData"]
    so_far = " so far" if today.year == year and today < dt.date(year, 12, 31) else ""
    grid = "\n".join(rects)

    # Type scale
    big = f"{total:,}"
    big_w = measure(big, "geist-sans-600", 96, -4.5)
    cap = f"CONTRIBUTIONS IN {year}{so_far.upper()}"
    cap_w = measure(cap, "geist-mono-500", 11.5, 1.6)
    stats, x = [], PAD + max(big_w, cap_w) + 56
    for value, label in ((str(streak), "DAY STREAK"), (top_lang, "TOP LANGUAGE")):
        stats.append(
            f'<line x1="{x - 28:.1f}" y1="160" x2="{x - 28:.1f}" y2="244" stroke="#21262d"/>\n'
            f'<text x="{x:.1f}" y="208" class="s" font-size="36" letter-spacing="-1" fill="#f0f6fc">{esc(value)}</text>\n'
            f'<text x="{x:.1f}" y="240" class="m" font-size="11.5" letter-spacing="1.6" fill="#7d8590">{label}</text>')
        x += max(measure(value, "geist-sans-600", 36, -1), measure(label, "geist-mono-500", 11.5, 1.6)) + 56

    faces = "".join(
        f'@font-face{{font-family:"{fam}";font-weight:{w};src:url(data:font/woff2;base64,{font_b64(f"{file}-{w}")}) format("woff2")}}'
        for fam, file, ws in (("G", "geist-sans", (500, 600)), ("GM", "geist-mono", (400, 500))) for w in ws)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{USER}'s {year} on GitHub: {total:,} contributions, {streak} day streak, top language {esc(top_lang)}">
<style>{faces}
.s{{font-family:"G",sans-serif;font-weight:600}}.n{{font-family:"G",sans-serif;font-weight:500}}
.m{{font-family:"GM",monospace;font-weight:500}}.h{{font-family:"GM",monospace;font-weight:400}}</style>
<defs>
<clipPath id="av"><circle cx="66" cy="70" r="22"/></clipPath>
<radialGradient id="glow" cx="0.82" cy="0.78" r="0.55"><stop offset="0" stop-color="#2ea043" stop-opacity="0.10"/><stop offset="1" stop-color="#2ea043" stop-opacity="0"/></radialGradient>
</defs>
<rect width="{W}" height="{H}" rx="14" fill="#0d1117"/>
<rect width="{W}" height="{H}" rx="14" fill="url(#glow)"/>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="#f0f6fc" stroke-opacity="0.08"/>
<image x="44" y="48" width="44" height="44" clip-path="url(#av)" xlink:href="{avatar}" href="{avatar}"/>
<circle cx="66" cy="70" r="22.5" fill="none" stroke="#f0f6fc" stroke-opacity="0.15"/>
<text x="102" y="66" class="s" font-size="18" letter-spacing="-0.2" fill="#f0f6fc">{name}</text>
<text x="102" y="87" class="h" font-size="13" fill="#7d8590">@{USER}</text>
<text x="{PAD - 4}" y="208" class="s" font-size="96" letter-spacing="-4.5" fill="#f0f6fc">{big}</text>
<text x="{PAD}" y="240" class="m" font-size="11.5" letter-spacing="1.6" fill="#7d8590">{cap}</text>
{chr(10).join(stats)}
{grid}
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
