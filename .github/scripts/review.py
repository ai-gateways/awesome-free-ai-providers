#!/usr/bin/env python3
"""Checks README.md against the rules in contributing.md.

Usage:
  review.py check [README.md] [--network] [--lint]  Check a local file.
  review.py format [README.md]                      Align table pipes in place.
  review.py pr --pr NUMBER [--lint] [--post]        Review a pull request and optionally post the result.
  review.py full [README.md] [--issue]              Check every entry, optionally update the health issue.

Uses only the Python standard library. Reads GITHUB_TOKEN (or GH_TOKEN) for GitHub API calls and
GITHUB_REPOSITORY for the repository (defaults to ai-gateways/awesome-free-ai-providers).
"""

import argparse
import concurrent.futures
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "ai-gateways/awesome-free-ai-providers")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
UA = "Mozilla/5.0 (compatible; awesome-free-ai-providers-review/1.0; +https://github.com/ai-gateways/awesome-free-ai-providers)"
COMMENT_MARKER = "<!-- awesome-free-ai-providers-review -->"
ISSUE_MARKER = "<!-- awesome-free-ai-providers-health -->"

PROVIDER_SECTIONS = [
    "Free Tiers",
    "Routers and Community Networks",
    "Signup and Trial Credits",
    "Cloud Trial Credits",
    "Mainland China Platforms",
    "Embeddings and Rerankers",
    "Speech",
]
OTHER_SECTIONS = {"Contents", "At a Glance", "Combining Free Tiers", "Contributing"}
FIELDS = ["Free", "Models", "Limits", "Requires", "OpenAI-compatible", "Data use", "Commercial use", "Verified"]
REQUIRED_FIELDS = {"Free", "Verified"}
CARD_VALUES = {"Yes", "No", "Not stated", "Usually no"}

STALE_DAYS = 90        # entries older than this are due for a re-check
PR_FRESH_DAYS = 14     # a changed entry should carry a Verified date this recent
MAX_DESCRIPTION = 200  # characters in the one-sentence description

# Pages that render with JavaScript or block automated requests. A missing anchor or a 403 here is
# a warning to check by hand, not an error.
SOFT_HOSTS = {
    "aistudio.google.com", "dataplatform.cloud.ibm.com", "cloud.tencent.com.cn",
    "platform.baichuan-ai.com", "modelscope.cn", "aihorde.net", "ai21.com", "scaleway.com",
}
MARKETING_WORDS = [
    "best", "fastest", "leading", "industry-leading", "world's", "world-class", "powerful",
    "blazing", "blazingly", "revolutionary", "next-gen", "next-generation", "state-of-the-art",
    "cutting-edge", "game-changer", "game-changing", "seamless", "seamlessly", "robust",
    "leverage", "leverages", "unlock", "unlocks", "supercharge", "supercharges", "effortless",
    "effortlessly", "ultimate", "unparalleled", "unmatched", "incredible", "amazing", "generous",
    "#1", "10x", "magical",
]
MARKETING_RE = re.compile(r"(?<![\w#-])(" + "|".join(re.escape(w) for w in MARKETING_WORDS) + r")(?![\w-])", re.I)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
END_DATE_RE = re.compile(r"\b(until|through|ends?|ending|expires?|expiring)\s+(?:on\s+)?(\d{4}-\d{2}-\d{2})", re.I)
CJK_RE = re.compile(r"[　-鿿가-힯＀-￯]")


def today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def slug(heading):
    return re.sub(r"\s", "-", re.sub(r"[^\w\- ]", "", heading.strip().lower()))


def url_key(url):
    p = urllib.parse.urlsplit(url)
    host = p.netloc.lower().removeprefix("www.")
    return host + p.path.rstrip("/") + ("?" + p.query if p.query else "")


def host_of(url):
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def site_of(url):
    """Registrable domain, so a redirect from www.example.com to docs.example.com counts as the same site."""
    parts = host_of(url).split(".")
    keep = 3 if len(parts) > 2 and parts[-2] in {"com", "co", "org", "net", "gov", "edu", "ac"} else 2
    return ".".join(parts[-keep:])


def cells(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


# ---------------------------------------------------------------- parsing

class Provider:
    def __init__(self, name, section, line_no):
        self.name, self.section, self.line_no = name, section, line_no
        self.desc, self.desc_line = None, None
        self.fields = {}          # field -> (text, line_no)
        self.field_order = []
        self.header_ok = None
        self.stray = []           # (line_no, text) lines that do not belong
        self.lines = []           # raw lines of the block

    @property
    def raw(self):
        return "\n".join(self.lines).strip()

    @property
    def verified(self):
        text = self.fields.get("Verified", ("", 0))[0]
        if DATE_RE.match(text):
            try:
                return datetime.date.fromisoformat(text)
            except ValueError:
                return None
        return None

    def links(self):
        out = []
        for text, no in [(self.desc or "", self.desc_line)] + list(self.fields.values()):
            out += [(u, no) for _, u in LINK_RE.findall(text) if u.startswith("http")]
        return out


class Doc:
    def __init__(self, text):
        self.text = text
        self.lines = text.splitlines()
        self.sections = []        # (name, line_no)
        self.providers = []
        self.glance = []          # (cells, line_no)
        self.glance_header_line = None
        self.parse()

    def parse(self):
        section, current, in_glance = None, None, False
        for no, line in enumerate(self.lines, 1):
            if line.startswith("## "):
                section, current = line[3:].strip(), None
                self.sections.append((section, no))
                in_glance = section == "At a Glance"
                continue
            if in_glance and line.startswith("|"):
                c = cells(line)
                if self.glance_header_line is None:
                    self.glance_header_line = no
                elif not all(re.fullmatch(r":?-+:?", x) for x in c):
                    self.glance.append((c, no))
                continue
            if line.startswith("### ") and section in PROVIDER_SECTIONS:
                current = Provider(line[4:].strip(), section, no)
                current.lines.append(line)
                self.providers.append(current)
                continue
            if current is None:
                continue
            current.lines.append(line)
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("|"):
                c = cells(stripped)
                if current.header_ok is None:
                    current.header_ok = c == ["Field", "Detail"]
                    continue
                if all(re.fullmatch(r":?-+:?", x) for x in c):
                    continue
                if len(c) != 2:
                    current.stray.append((no, "Table rows need exactly two cells: `| Field | Detail |`."))
                    continue
                field, value = c
                if field in current.fields:
                    current.stray.append((no, f"Field `{field}` appears twice."))
                current.fields[field] = (value, no)
                current.field_order.append(field)
            elif current.desc is None and current.header_ok is None:
                current.desc, current.desc_line = stripped, no
            else:
                current.stray.append((no, "Unexpected text. Each entry is a heading, one sentence, and a Field and Detail table."))

    def links(self):
        """All external links with line numbers, outside code spans."""
        out = []
        for no, line in enumerate(self.lines, 1):
            for _, u in LINK_RE.findall(re.sub(r"`[^`]*`", "", line)):
                if u.startswith("http"):
                    out.append((u, no))
        return out


# ---------------------------------------------------------------- static checks

def provider_findings(p):
    """Returns a list of (level, message) for one provider entry."""
    out = []
    if not p.desc:
        out.append(("error", "Missing the one-sentence description under the heading."))
    else:
        if not re.match(r"[A-Z0-9`\"$]", p.desc):
            out.append(("error", "Description must start with an uppercase letter."))
        if not p.desc.endswith("."):
            out.append(("error", "Description must end with a period."))
        if re.search(r"[.!?] [A-Z]", p.desc[:-1]):
            out.append(("warning", "Description looks like more than one sentence."))
        if len(p.desc) > MAX_DESCRIPTION:
            out.append(("warning", f"Description is {len(p.desc)} characters; keep it under {MAX_DESCRIPTION}."))
        if p.desc.lower().startswith(p.name.lower()):
            out.append(("warning", "Description repeats the name. Start with what is free."))
    if p.header_ok is None:
        out.append(("error", "Missing the `| Field | Detail |` table."))
    elif not p.header_ok:
        out.append(("error", "Table header must be `| Field | Detail |`."))
    for field in p.field_order:
        if field not in FIELDS:
            out.append(("error", f"Unknown field `{field}`. Use: " + ", ".join(f"`{f}`" for f in FIELDS) + "."))
    for field in sorted(REQUIRED_FIELDS - set(p.fields), key=FIELDS.index):
        out.append(("error", f"Missing the `{field}` row."))
    known = [f for f in p.field_order if f in FIELDS]
    if known != sorted(known, key=FIELDS.index):
        out.append(("error", "Rows are out of order. Use: " + ", ".join(FIELDS) + " (skip rows that do not apply)."))
    free = p.fields.get("Free", ("", 0))[0]
    if free and not any(u.startswith("http") for _, u in LINK_RE.findall(free)):
        out.append(("error", "The `Free` row must link the provider's page that states the free offer."))
    if "Verified" in p.fields:
        text = p.fields["Verified"][0]
        if not DATE_RE.match(text) or p.verified is None:
            out.append(("error", f"`Verified` must be a date in YYYY-MM-DD form, not `{text}`."))
        elif p.verified > today() + datetime.timedelta(days=1):
            out.append(("error", f"`Verified` date {text} is in the future."))
    texts = [p.desc or ""] + [v for v, _ in p.fields.values()]
    words = sorted({m.group(1).lower() for t in texts for m in MARKETING_RE.finditer(LINK_RE.sub(r"\1", t))})
    if words:
        out.append(("error", "Marketing language: " + ", ".join(f"`{w}`" for w in words) + ". State the facts instead."))
    for u, _ in p.links():
        if "#" not in u and not u.endswith(".pdf") and "/api/" not in u and not u.endswith("/models"):
            out.append(("warning", f"Link has no section anchor: <{u}>. Add a heading anchor or a `#:~:text=` fragment."))
    for no, msg in p.stray:
        out.append(("error", f"Line {no}: {msg}"))
    return out


def due_findings(p):
    """Re-check reminders: stale Verified dates and end dates that have passed."""
    out = []
    if p.verified and (today() - p.verified).days > STALE_DAYS:
        out.append(f"Verified {(today() - p.verified).days} days ago ({p.verified}).")
    for text, _ in p.fields.values():
        for m in END_DATE_RE.finditer(text):
            try:
                end = datetime.date.fromisoformat(m.group(2))
            except ValueError:
                continue
            if end < today():
                out.append(f"Says the offer runs {m.group(1).lower()} {end}, which has passed.")
            elif (end - today()).days <= 14:
                out.append(f"Says the offer runs {m.group(1).lower()} {end}, {(end - today()).days} days from now.")
    return out


def global_findings(doc):
    """Returns (by_provider, general). by_provider maps provider name to [(level, message)]."""
    by, general = {}, []
    add = lambda name, level, msg: by.setdefault(name, []).append((level, msg))

    names = [p.name for p in doc.providers]
    seen = {}
    for p in doc.providers:
        key = p.name.lower()
        if key in seen:
            add(p.name, "error", f"Duplicate entry; `{seen[key].name}` is already in {seen[key].section}.")
        seen.setdefault(key, p)

    for section in PROVIDER_SECTIONS:
        items = [p for p in doc.providers if p.section == section]
        got = [p.name.lower() for p in items]
        if got != sorted(got):
            want = sorted(items, key=lambda p: p.name.lower())
            for i, p in enumerate(items):
                if p is not want[i]:
                    after = want[want.index(p) - 1].name if want.index(p) > 0 else None
                    add(p.name, "error", f"Out of alphabetical order in {section}; it belongs " + (f"after `{after}`." if after else "at the top."))

    known = set(PROVIDER_SECTIONS) | OTHER_SECTIONS
    for name, no in doc.sections:
        if name not in known:
            general.append(("warning", f"Line {no}: section `{name}` is not known to the checker; add it to .github/scripts/review.py."))

    rows = {}
    for c, no in doc.glance:
        m = re.fullmatch(r"\[([^\]]+)\]\(#([^)]+)\)", c[0]) if c else None
        if len(c) != 4 or not m:
            general.append(("error", f"Line {no}: At a Glance rows need four cells and start with `[Name](#anchor)`."))
            continue
        rows[m.group(1)] = (m.group(2), c, no)
        if c[2] not in CARD_VALUES:
            general.append(("warning", f"Line {no}: `Card needed` is `{c[2]}`; use one of " + ", ".join(f"`{v}`" for v in sorted(CARD_VALUES)) + "."))
    for p in doc.providers:
        if p.name not in rows:
            add(p.name, "error", "Missing its row in the At a Glance table.")
        elif rows[p.name][0] != slug(p.name):
            add(p.name, "error", f"At a Glance link should be `#{slug(p.name)}`, not `#{rows[p.name][0]}`.")
    for name, (_, _, no) in rows.items():
        if name not in names:
            general.append(("error", f"Line {no}: At a Glance row `{name}` has no matching entry heading."))
    glance_names = [c[0] for c, _ in doc.glance]
    order = [re.sub(r"\]\(.*", "", n).lstrip("[").lower() for n in glance_names]
    if order != sorted(order):
        general.append(("error", "At a Glance rows are not in alphabetical order (ignoring case)."))

    first = {}
    for u, no in doc.links():
        k = url_key(u)
        if k in first:
            owner = next((p.name for p in doc.providers if p.line_no <= no and no - p.line_no < len(p.lines)), None)
            where = "earlier on the same line" if first[k][1] == no else f"on line {first[k][1]}"
            msg = f"Line {no} links a page already linked {where}: <{u.split('#')[0]}>. awesome-lint counts any two links to one page as duplicates, even with different anchors; cite the page once."
            (add(owner, "error", msg) if owner else general.append(("error", msg)))
        first.setdefault(k, (u, no))

    for no, line in enumerate(doc.lines, 1):
        if "—" in line or "–" in line:
            general.append(("error", f"Line {no}: em dash or en dash. Use a comma, colon, or parentheses."))
        if CJK_RE.search(line):
            general.append(("error", f"Line {no}: Chinese, Japanese, or Korean characters break table alignment. Translate the text; keep the original only in the link's URL."))
    general += alignment_findings(doc.lines)
    return by, general


def alignment_findings(lines):
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            block = lines[i:j]
            if len({tuple(m.start() for m in re.finditer(r"(?<!\\)\|", l)) for l in block}) > 1:
                out.append(("error", f"Line {i + 1}: table pipes do not line up. Run `python3 .github/scripts/review.py format README.md`."))
            i = j
        else:
            i += 1
    return out


def format_tables(text):
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        if not lines[i].startswith("|"):
            out.append(lines[i]); i += 1; continue
        j = i
        while j < len(lines) and lines[j].startswith("|"):
            j += 1
        rows = [cells(l) for l in lines[i:j]]
        n = max(len(r) for r in rows)
        rows = [r + [""] * (n - len(r)) for r in rows]
        sep = lambda r: all(re.fullmatch(r":?-+:?", x) for x in r if x)
        width = [max([3] + [len(r[k]) for r in rows if not sep(r)]) for k in range(n)]
        for r in rows:
            out.append("| " + " | ".join(("-" * width[k]) if sep(r) else r[k].ljust(width[k]) for k in range(n)) + " |")
        i = j
    return "\n".join(out)


# ---------------------------------------------------------------- network checks

def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "ignore")


def gh_api(path, method="GET", data=None, accept="application/vnd.github+json"):
    url = path if path.startswith("http") else f"https://api.github.com/{path.lstrip('/')}"
    headers = {"User-Agent": UA, "Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(data).encode() if data is not None else None
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "ignore")
        if accept.endswith("raw"):
            return raw
        return json.loads(raw) if raw else None


def page_text(body):
    body = re.sub(r"(?s)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip().lower()


def fragment_found(body, fragment, raw=False):
    if fragment.startswith(":~:text="):
        phrase = urllib.parse.unquote(fragment[len(":~:text="):])
        parts = [x for x in phrase.split(",") if not x.endswith("-") and not x.startswith("-")]
        phrase = re.sub(r"\s+", " ", (parts[0] if parts else phrase)).strip().lower()
        text = re.sub(r"\s+", " ", body).lower() if raw else page_text(body)
        return phrase in text or phrase in re.sub(r"\s+", " ", html.unescape(body)).lower()
    frag = re.escape(urllib.parse.unquote(fragment))
    return re.search(r"""\b(?:id|name)=["']?(?:user-content-)?""" + frag + r"""["'\s>]""", body.replace("&amp;", "&")) is not None


_cache = {}


def fetch(url):
    if url not in _cache:
        result = None
        for _ in range(2):
            try:
                result = http_get(url)
                break
            except urllib.error.HTTPError as e:
                result = ("http", e.code)
                if e.code in (404, 410):
                    break
            except Exception as e:  # DNS, TLS, timeout
                result = ("err", str(e)[:80])
        _cache[url] = result
    return _cache[url]


def check_link(url):
    """Returns a list of (level, message)."""
    base, _, fragment = url.partition("#")
    soft = host_of(base) in SOFT_HOSTS
    result = fetch(base)
    if result[0] == "http":
        code = result[1]
        if code in (404, 410):
            return [("error", f"Link returns HTTP {code}: <{base}>")]
        return [("warning", f"Could not verify <{base}> (HTTP {code}, often bot protection). Open it in a browser.")]
    if result[0] == "err":
        return [("warning", f"Could not reach <{base}> ({result[1]}).")]
    _, final, body = result
    out = []
    if site_of(final) != site_of(base):
        out.append(("warning", f"<{base}> redirects to another site: <{final}>. Link the final page."))
    if not fragment or fragment.startswith("page=") or re.fullmatch(r"L\d+(-L\d+)?", fragment):
        return out
    raw = False
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/(.+)$", base)
    if m and fragment.startswith(":~:text="):
        r = fetch(f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}")
        if r[0] not in ("http", "err"):
            body, raw = r[2], True
    if not fragment_found(body, fragment, raw):
        if soft:
            out.append(("warning", f"Could not confirm `#{fragment[:60]}` on <{base}>; the page renders with JavaScript. Check it in a browser."))
        else:
            out.append(("error", f"`#{fragment[:60]}` was not found on <{base}>. Use a heading anchor that exists on the page or a `#:~:text=` fragment with exact page text."))
    return out


def network_findings(providers):
    """Returns {provider name: [(level, message)]}."""
    jobs = {}
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        for p in providers:
            jobs[p.name] = [pool.submit(check_link, u) for u, _ in p.links()]
        return {name: [f for fut in futs for f in fut.result()] for name, futs in jobs.items()}


# ---------------------------------------------------------------- awesome-lint

IGNORED_LINT_RULES = ("awesome-git-repo-age", "awesome-github")


def run_awesome_lint(readme_text, lint_cmd):
    """Runs awesome-lint on the text in a scratch git repo. Returns (ok, findings)."""
    tmp = tempfile.mkdtemp()
    try:
        with open(os.path.join(tmp, "readme.md"), "w") as f:
            f.write(readme_text)
        with open(os.path.join(tmp, "contributing.md"), "w") as f:
            f.write("# Contribution Guidelines\n")
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"], cwd=tmp, check=True)
        p = subprocess.run(lint_cmd + ["readme.md"], cwd=tmp, capture_output=True, text=True, timeout=300)
        text = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout + p.stderr)
        lines = [l.strip() for l in text.splitlines() if re.match(r"\s*[✖⚠]\s+\d+:\d+", l)]
        lines = [l for l in lines if not l.endswith(IGNORED_LINT_RULES)]
        return not any(l.startswith("✖") for l in lines), lines
    except Exception as e:
        return True, [f"⚠ awesome-lint did not run: {e}"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- reports

ICON = {"error": "❌", "warning": "⚠️"}


def esc(text):
    text = re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)
    return text.replace("@", "@​")


def block(name, where, findings):
    lines = [f"**{esc(name)}** {where}", ""]
    lines += [f"- {ICON[l]} {m}" for l, m in findings] if findings else ["- ✅ No problems found."]
    return "\n".join(lines)


def count(groups):
    levels = [l for findings in groups for l, _ in findings]
    return levels.count("error"), levels.count("warning")


def review_doc(doc, providers, network):
    """Findings for the given providers plus document-wide findings."""
    by, general = global_findings(doc)
    net = network_findings(providers) if network else {}
    results = []
    for p in providers:
        f = provider_findings(p) + by.get(p.name, []) + net.get(p.name, [])
        results.append((p, f))
    return results, general


# ---------------------------------------------------------------- commands

def cmd_check(args):
    text = open(args.readme, encoding="utf-8").read()
    doc = Doc(text)
    results, general = review_doc(doc, doc.providers, args.network)
    for p, f in results:
        for level, msg in f:
            print(f"{args.readme}:{p.line_no}: {level}: [{p.name}] {msg}")
        for msg in due_findings(p):
            print(f"{args.readme}:{p.line_no}: due: [{p.name}] {msg}")
    for level, msg in general:
        print(f"{args.readme}: {level}: {msg}")
    lint_ok = True
    if args.lint:
        lint_ok, lines = run_awesome_lint(text, args.lint_cmd.split())
        for l in lines:
            print(f"awesome-lint: {l}")
    errors, warnings = count([f for _, f in results] + [general])
    print(f"{len(doc.providers)} providers, {errors} errors, {warnings} warnings" + ("" if lint_ok else ", awesome-lint failed"))
    return 1 if errors or not lint_ok else 0


def cmd_format(args):
    text = open(args.readme, encoding="utf-8").read()
    new = format_tables(text)
    if new != text:
        open(args.readme, "w", encoding="utf-8").write(new)
        print(f"Aligned tables in {args.readme}.")
    else:
        print("Tables already aligned.")
    return 0


def fetch_pr(number):
    pr = gh_api(f"repos/{REPO}/pulls/{number}")
    files = gh_api(f"repos/{REPO}/pulls/{number}/files?per_page=100")
    readme_changed = any(f["filename"] == "README.md" for f in files)
    head = gh_api(f"repos/{REPO}/contents/README.md?ref={pr['head']['sha']}", accept="application/vnd.github.raw") if readme_changed else None
    base = gh_api(f"repos/{REPO}/contents/README.md?ref={pr['base']['sha']}", accept="application/vnd.github.raw")
    return pr, files, base, head


def outside_entries(doc):
    """README text outside provider entries, the At a Glance rows, and blank lines."""
    skip = set()
    for p in doc.providers:
        skip.update(range(p.line_no, p.line_no + len(p.lines)))
    skip.update(no for _, no in doc.glance)
    return [l for no, l in enumerate(doc.lines, 1) if no not in skip and l.strip()]


def pr_level_findings(pr, files, base, head, added, changed, removed):
    out = []
    other = sorted(f["filename"] for f in files if f["filename"] != "README.md")
    if other:
        out.append(("warning", "Changes files other than README.md: " + ", ".join(f"`{esc(o)}`" for o in other) + ". A maintainer will check these by hand."))
    if len(added) > 1:
        out.append(("warning", f"Adds {len(added)} providers. Open one pull request per provider so each can be reviewed on its own."))
    if not re.match(r"^(Add|Update|Remove|Move|Fix|Rename):? \S", pr.get("title") or ""):
        out.append(("warning", "Use a title such as `Add Name`, `Update Name limits`, or `Remove Name`."))
    body = (pr.get("body") or "").lower()
    if (added or changed) and not re.search(r"affiliation|i work (on|at|for)|i am (the|a) (author|maintainer|founder|employee)|i maintain|not affiliated|no affiliation|no connection", body):
        out.append(("warning", "Say how you are connected to the provider (for example `I work there` or `No affiliation`)."))
    for p in removed:
        out.append(("warning", f"Removes `{esc(p.name)}`. Link the page that shows the free offer ended."))
    if head is not None and outside_entries(Doc(base)) != outside_entries(head):
        out.append(("warning", "Changes text outside the provider entries (intro, Combining Free Tiers, or Contents). A maintainer will review it by hand."))
    return out


def build_pr_report(results, general, pr_findings, lint, added_names):
    errors, warnings = count([f for _, f in results] + [general, pr_findings])
    if lint and not lint[0]:
        errors += 1
    if errors:
        head = f"### ❌ {errors} problem{'s' if errors != 1 else ''} to fix" + (f", {warnings} warning{'s' if warnings != 1 else ''}" if warnings else "")
    elif warnings:
        head = f"### ⚠️ No blocking problems, {warnings} warning{'s' if warnings != 1 else ''} to look at"
    else:
        head = "### ✅ All automated checks passed"
    parts = [COMMENT_MARKER, "## Automated review", "", head, ""]
    if not results:
        parts += ["No provider entries were added or changed in README.md.", ""]
    for p, f in results:
        what = "new entry" if p.name in added_names else "changed entry"
        parts += [block(p.name, f"({what} in {p.section}, line {p.line_no})", f), ""]
    if general:
        parts += ["**Whole list**", ""] + [f"- {ICON[l]} {m}" for l, m in general[:20]] + [""]
    if pr_findings:
        parts += ["**Pull request**", ""] + [f"- {ICON[l]} {m}" for l, m in pr_findings] + [""]
    if lint is not None:
        ok, lines = lint
        parts += ["**awesome-lint**", ""]
        parts += ["- ✅ No problems."] if not lines else [f"- {'❌' if l.startswith('✖') else '⚠️'} `{esc(l[1:].strip())}`" for l in lines[:15]]
        parts.append("")
    parts += [
        "<details><summary>What a maintainer checks next</summary>",
        "",
        "- Open each source link and confirm the page states the fact in that row, including limits and amounts.",
        "- The free offer is live today, documented on a public page, and run by a named operator.",
        "- The entry sits in the right section, and the At a Glance row matches it.",
        "- If the provider publishes token caps or one-time token grants, the Combining Free Tiers totals are updated.",
        "- The pull request discloses any affiliation.",
        "",
        "</details>",
        "",
        f"<sub>Checks follow [contributing.md](https://github.com/{REPO}/blob/main/contributing.md#entry-format). Fix table alignment with `python3 .github/scripts/review.py format README.md`. This comment updates on every push.</sub>",
    ]
    return "\n".join(parts), errors, warnings


def upsert_comment(number, body):
    comments = gh_api(f"repos/{REPO}/issues/{number}/comments?per_page=100")
    mine = [c for c in comments if COMMENT_MARKER in (c.get("body") or "") and c["user"]["type"] == "Bot"]
    if mine:
        gh_api(f"repos/{REPO}/issues/comments/{mine[0]['id']}", "PATCH", {"body": body})
    else:
        gh_api(f"repos/{REPO}/issues/{number}/comments", "POST", {"body": body})


def set_labels(number, add, remove):
    current = {l["name"] for l in gh_api(f"repos/{REPO}/issues/{number}/labels")}
    for name in remove & current:
        try:
            gh_api(f"repos/{REPO}/issues/{number}/labels/{urllib.parse.quote(name)}", "DELETE")
        except urllib.error.HTTPError:
            pass
    if add - current:
        gh_api(f"repos/{REPO}/issues/{number}/labels", "POST", {"labels": sorted(add - current)})


def cmd_pr(args):
    pr, files, base_text, head_text = fetch_pr(args.pr)
    base = Doc(base_text)
    if head_text is None:
        results, general, added, changed, removed, head = [], [], [], [], [], None
    else:
        head = Doc(head_text)
        base_by = {p.name: p for p in base.providers}
        head_names = {p.name for p in head.providers}
        added = [p for p in head.providers if p.name not in base_by]
        changed = [p for p in head.providers if p.name in base_by and p.raw != base_by[p.name].raw]
        removed = [p for p in base.providers if p.name not in head_names]
        results, general = review_doc(head, added + changed, network=True)
        for p, f in results:
            old = base_by.get(p.name)
            if old and old.verified == p.verified:
                f.append(("warning", "The entry changed but its `Verified` date did not. Re-check the sources and set today's date."))
            if p.verified and (today() - p.verified).days > PR_FRESH_DAYS:
                f.append(("warning", f"`Verified` is {p.verified}; set it to the date you checked the sources."))
        base_general = {m for _, m in global_findings(base)[1]}
        general = [(l, m) for l, m in general if m not in base_general]
    pr_findings = pr_level_findings(pr, files, base_text, head, added, changed, removed)
    lint = run_awesome_lint(head_text, args.lint_cmd.split()) if args.lint and head_text is not None else None
    report, errors, _ = build_pr_report(results, general, pr_findings, lint, {p.name for p in added})
    print(report)
    if args.post:
        upsert_comment(args.pr, report)
        labels = {"needs changes"} if errors else {"ready for review"}
        if added:
            labels.add("new entry")
        if changed or removed:
            labels.add("entry update")
        set_labels(args.pr, labels, {"needs changes", "ready for review"} - labels)
    if args.summary and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report.replace(COMMENT_MARKER, "") + "\n")
    return 1 if errors else 0


def cmd_full(args):
    text = open(args.readme, encoding="utf-8").read()
    doc = Doc(text)
    results, general = review_doc(doc, doc.providers, network=True)
    errs = [(p, [x for x in f if x[0] == "error"]) for p, f in results]
    errs = [(p, f) for p, f in errs if f]
    general_errs = [x for x in general if x[0] == "error"]
    due = [(p, d) for p in doc.providers for d in [due_findings(p)] if d]
    errors, warnings = count([f for _, f in results] + [general])
    date = today().isoformat()
    lines = [ISSUE_MARKER, f"Check of {len(doc.providers)} providers on {date}: {errors} errors, {len(due)} due for a re-check, {warnings} warnings (warnings are in the workflow run summary).", ""]
    if errs or general_errs:
        lines += ["## Errors", "", "Broken links, missing anchors, or format problems on main. Fix these first.", ""]
        lines += [block(p.name, f"({p.section}, line {p.line_no})", f) + "\n" for p, f in errs]
        lines += [f"- {ICON[l]} {m}" for l, m in general_errs]
        lines.append("")
    if due:
        lines += ["## Due for a re-check", "", "Open the entry's source links, update anything that changed, and set `Verified` to today's date.", ""]
        lines += [f"- [ ] **{esc(p.name)}** ({p.section}): " + " ".join(d) for p, d in due]
        lines.append("")
    if not (errs or general_errs or due):
        lines.append("No errors and nothing due for a re-check.")
    report = "\n".join(lines)
    full_report = report
    warn = [(p, [x for x in f if x[0] == "warning"]) for p, f in results]
    warn = [(p, f) for p, f in warn if f]
    if warn:
        full_report += "\n\n## Warnings\n\n" + "\n\n".join(block(p.name, f"({p.section})", f) for p, f in warn)
    print(full_report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(full_report.replace(ISSUE_MARKER, "") + "\n")
    if args.issue:
        issues = gh_api(f"repos/{REPO}/issues?state=open&labels=maintenance&per_page=50")
        mine = [i for i in issues if ISSUE_MARKER in (i.get("body") or "")]
        if (errs or general_errs or due) and mine:
            gh_api(f"repos/{REPO}/issues/{mine[0]['number']}", "PATCH", {"body": report})
        elif errs or general_errs or due:
            gh_api(f"repos/{REPO}/issues", "POST", {"title": "List health report", "body": report, "labels": ["maintenance"]})
        elif mine:
            gh_api(f"repos/{REPO}/issues/{mine[0]['number']}/comments", "POST", {"body": f"No errors and nothing due in the check on {date}. Closing."})
            gh_api(f"repos/{REPO}/issues/{mine[0]['number']}", "PATCH", {"state": "closed"})
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("readme", nargs="?", default="README.md")
    c.add_argument("--network", action="store_true", help="also load every link and check its anchor")
    c.add_argument("--lint", action="store_true", help="also run awesome-lint (needs Node.js)")
    c.add_argument("--lint-cmd", default="npx --yes awesome-lint@2.3.0")
    fm = sub.add_parser("format")
    fm.add_argument("readme", nargs="?", default="README.md")
    p = sub.add_parser("pr")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--lint", action="store_true", help="run awesome-lint on the pull request README")
    p.add_argument("--lint-cmd", default="npx --yes awesome-lint@2.3.0")
    p.add_argument("--post", action="store_true", help="post or update the review comment and labels")
    p.add_argument("--summary", action="store_true", help="write the report to the job summary")
    f = sub.add_parser("full")
    f.add_argument("readme", nargs="?", default="README.md")
    f.add_argument("--issue", action="store_true", help="open, update, or close the health report issue")
    args = ap.parse_args()
    sys.exit({"check": cmd_check, "format": cmd_format, "pr": cmd_pr, "full": cmd_full}[args.cmd](args))


if __name__ == "__main__":
    main()
