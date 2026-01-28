# generator/build.py
# ZinkNET — GitHub Actions builder (Google Sheet -> static site in /docs)
# Adds:
# - Instrumentation Search Tool builder (existing)
# - RISM fields from Google Sheet: RISM Holdings, RISM Date (display+search), RISM Earliest/Latest Year (filter only)
# - Index: RISM date chip + chronology filter (From/To) based on earliest/latest, hidden from UI
# - Detail page: RISM drawer (variant B-style) showing RISM Date + Holdings (earliest/latest not shown)

import re, html, shutil, json
from pathlib import Path
import pandas as pd

# =========================
# CONFIG
# =========================
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1XrARBpah9CL_BMj3XRsyw1CL5o8RVheDyuAg5ya0z4I/gviz/tq?tqx=out:csv&sheet=NEW%20MERGED%20FILE"

OUT_DIR = Path("docs")            # GitHub Pages: publish /docs
ASSETS_SRC = Path("assets_src")   # put hem.png + rism.png here
HEM_LOGO = "hem.png"
RISM_LOGO = "rism.png"

EM_TITLES = [
    "The Early Trombone : a Catalog of Music",
    "Instrumental Music Specifying Cornett",
    "A Catalog of Music for the Cornett",
    "The Early Trombone",
    "Instrumental Music",
    "Vocal Music",
]
EM_TITLES_SORTED = sorted(EM_TITLES, key=len, reverse=True)

# =========================
# HELPERS
# =========================
def clean_str(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

def clean_numberish(val):
    """Turn numeric-like ids into clean strings (avoid 123.0)."""
    if pd.isna(val) or val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    s = str(val).strip()
    s = re.sub(r"\.0$", "", s)
    return "" if s.lower() == "nan" else s

def escape_textnode(val):
    s = clean_str(val)
    if not s:
        return ""
    return html.escape(s, quote=False).replace("\n", "<br>")

def escape_attr(val):
    s = clean_str(val)
    if not s:
        return ""
    return html.escape(s, quote=True)

def escape_with_italics(text):
    s = clean_str(text)
    if not s:
        return ""
    placeholders = {}
    for i, title in enumerate(EM_TITLES_SORTED):
        if title in s:
            key = f"§§EM{i}§§"
            s = s.replace(title, key)
            placeholders[key] = title
    esc = html.escape(s, quote=False).replace("\n", "<br>")
    for key, title in placeholders.items():
        esc = esc.replace(key, f"<em>{html.escape(title, quote=False)}</em>")
    return esc

def strip_see_rism(text):
    s = clean_str(text)
    if not s:
        return "", False
    flag = False
    for p in ("See RISM", "see RISM", "[See RISM]", "[see RISM]"):
        if p in s:
            flag = True
            s = s.replace(p, "")
    s = re.sub(r"\[\s*\]", "", s)
    s = re.sub(r"\s*\n\s*", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s, flag

def parse_conc_ids(s):
    s = clean_str(s)
    if not s:
        return []
    txt = s.replace("[", "").replace("]", "")
    parts = re.split(r"[;,\n]+", txt)
    return [p.strip() for p in parts if p.strip()]

def format_uniform_instr(raw_text, alternative=False):
    """
    Any 'LABEL: { ... }' becomes its own line block (braces removed).
    Works for ChI but also any other label pattern followed by ': {'
    """
    s = clean_str(raw_text)
    if not s:
        return ""

    def repl(m):
        label = m.group(1).strip()
        content = m.group(2).strip()
        return f"\n{label} {content}\n"

    t2 = re.sub(r'([^:]+:\s*)\{([^}]*)\}', repl, s)   # remove braces, insert breaks
    t2 = re.sub(r'\n\s*,\s*', '\n', t2)
    t2 = re.sub(r'\n+', '\n', t2).strip(' \n,')
    if not t2.strip():
        return ""

    heading = "UNIFORM INSTRUMENTATION (ALTERNATIVE)" if alternative else "UNIFORM INSTRUMENTATION"
    body = html.escape(t2, quote=False).replace("\n", "<br>")
    return f'<strong class="instr-label">{heading}</strong><div class="instr-content">{body}</div>'

def parse_zinknet(no):
    s = clean_str(no)
    if not s:
        return (10**9, 10**9)
    if "/" in s:
        a, b = s.split("/", 1)
        try:
            return (int(a), int(b))
        except ValueError:
            return (10**9, 10**9)
    try:
        return (int(s), 0)
    except ValueError:
        return (10**9, 10**9)

def group_id(no):
    s = clean_str(no)
    return s.split("/", 1)[0] if "/" in s else s

def get_col(row, name):
    return row[name] if (name in row and not pd.isna(row[name])) else ""

def norm_music_type(s):
    """
    Keep ONLY canonical ZinkNET values:
      - Instrumental
      - Vocal / Mixed
      - Instrumental / Vocal / Mixed
    """
    t = clean_str(s)
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t.strip())

    CANON = {
        "Instrumental",
        "Vocal / Mixed",
        "Instrumental / Vocal / Mixed",
    }
    if t in CANON:
        return t

    low = t.lower().replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
    if ("instrumental" in low) and ("vocal" in low) and ("mixed" in low):
        return "Instrumental / Vocal / Mixed"
    if ("vocal" in low) and ("mixed" in low):
        return "Vocal / Mixed"
    if ("instrumental" in low) and ("mixed" in low) and ("vocal" not in low):
        return "Instrumental"

    return t

def norm_url(u):
    return clean_str(u).strip()

def parse_int_safe(x):
    x = clean_numberish(x)
    if not x:
        return None
    try:
        return int(x)
    except ValueError:
        return None

# =========================
# Search Tool parser
# =========================
def _split_top_level(s, sep):
    """Split by sep only when not inside brackets []"""
    out, buf, depth = [], [], 0
    for ch in s:
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth = max(depth - 1, 0)
        if ch == sep and depth == 0:
            part = "".join(buf).strip()
            if part:
                out.append(part)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out

_item_re = re.compile(r'^\s*([^\(\)\[\]]+?)\s*\(\s*(\d+)\s*\)\s*$')

def _parse_item_token(tok):
    """Parse 'org (1)' -> ('org', 1). Return None if not matching."""
    m = _item_re.match(tok.strip())
    if not m:
        return None
    name = m.group(1).strip()
    qty = int(m.group(2))
    return name, qty

def _strip_outer_brackets(s):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        return s[1:-1].strip()
    return s

def _parse_choice_block(block):
    """
    Parse '[arpa/lute (1)]' -> (['arpa','lute'], 1)
    """
    inner = _strip_outer_brackets(block)
    m2 = re.match(r'^(.*)\(\s*(\d+)\s*\)\s*$', inner)
    if not m2:
        return None
    alts_part = m2.group(1).strip()
    qty = int(m2.group(2))
    alts = [a.strip() for a in _split_top_level(alts_part, "/")]
    alts = [a for a in alts if a]
    return alts, qty

def _parse_branch(branch_block):
    """
    Parse a branch like:
    [V (2) + [cnto/vl (3)] + [trb/i (3)]]
    Returns:
      base_items: dict instrument->qty (mandatory)
      choices: list of (alts list, qty)
    """
    inner = _strip_outer_brackets(branch_block)
    parts = [p.strip() for p in _split_top_level(inner, "+")]
    base_items = {}
    choices = []
    for p in parts:
        if not p:
            continue
        if p.startswith("[") and p.endswith("]"):
            ch = _parse_choice_block(p)
            if ch:
                choices.append(ch)
        else:
            it = _parse_item_token(p)
            if it:
                name, qty = it
                base_items[name] = base_items.get(name, 0) + qty
    return base_items, choices

def _expand_choices(base_items, choices, limit=256):
    """
    Enumerate scenarios by choosing one alt from each choice group.
    limit avoids explosion; if exceeded we stop.
    Returns list of dict instrument->qty
    """
    scenarios = [dict(base_items)]
    for alts, qty in choices:
        new = []
        for sc in scenarios:
            for a in alts:
                sc2 = dict(sc)
                sc2[a] = sc2.get(a, 0) + qty
                new.append(sc2)
                if len(new) >= limit:
                    break
            if len(new) >= limit:
                break
        scenarios = new
        if len(scenarios) >= limit:
            break
    return scenarios

def parse_search_tool_to_scenarios(text, limit=256):
    """
    Grammar:
      - comma-separated top-level items
      - may contain ONE top-level branch expression: [branchA] / [branchB] / ...
      - branch content uses '+' for co-presence and [a/b (n)] choices
    Returns list of scenarios: list[dict instr->qty]
    """
    s = clean_str(text)
    if not s:
        return []
    s = re.sub(r"\s+", " ", s).strip()
    top = _split_top_level(s, ",")

    # Detect one top-level branch segment, of the form: [ ... ] / [ ... ] ...
    branch_blocks = None
    branch_seg_idx = None
    for i, seg in enumerate(top):
        seg = seg.strip()
        if seg.startswith("[") and seg.endswith("]") and "/" in seg:
            parts = _split_top_level(seg, "/")
            if len(parts) >= 2 and all(p.strip().startswith("[") and p.strip().endswith("]") for p in parts):
                branch_blocks = [p.strip() for p in parts]
                branch_seg_idx = i
                break

    scenarios = []

    if branch_blocks:
        # common items are the item tokens outside the branch segment
        common_items = {}
        for j, seg in enumerate(top):
            if j == branch_seg_idx:
                continue
            it = _parse_item_token(seg)
            if it:
                name, qty = it
                common_items[name] = common_items.get(name, 0) + qty

        for bb in branch_blocks:
            base, choices = _parse_branch(bb)
            base2 = dict(common_items)
            for k, v in base.items():
                base2[k] = base2.get(k, 0) + v
            scenarios.extend(_expand_choices(base2, choices, limit=limit))
    else:
        # no top-level branches: parse once (no double-counting)
        base = {}
        choices = []
        for seg in top:
            seg = seg.strip()
            if not seg:
                continue
            if seg.startswith("[") and seg.endswith("]"):
                ch = _parse_choice_block(seg)
                if ch:
                    choices.append(ch)
            else:
                it = _parse_item_token(seg)
                if it:
                    name, qty = it
                    base[name] = base.get(name, 0) + qty
        scenarios = _expand_choices(base, choices, limit=limit)

    # Deduplicate scenarios
    seen = set()
    uniq = []
    for sc in scenarios:
        key = tuple(sorted(sc.items()))
        if key not in seen:
            seen.add(key)
            uniq.append(sc)
    return uniq

# =========================
# RISM CHIPS
# =========================
def rism_chip_unique(link, text, used_links=None):
    link = norm_url(link)
    if not link:
        return ""
    if used_links is not None and link in used_links:
        return ""
    if used_links is not None:
        used_links.add(link)
    return f'<a class="tag tag-rism" href="{escape_attr(link)}" target="_blank" rel="noopener">{escape_textnode(text)}</a>'

def rism_chip_self(rec, used_links=None):
    link = norm_url(rec.get("rism_link_raw", ""))
    if not link:
        return ""
    return rism_chip_unique(link, "RISM Online", used_links)

def rism_chip_collection(parent_rec, used_links=None):
    link = norm_url(parent_rec.get("rism_link_raw", ""))
    if not link:
        return ""
    return rism_chip_unique(link, "RISM Online (Collection)", used_links)

def rism_duo(self_chip_html, coll_chip_html):
    """Elegant double-chip wrapper with a thin divider."""
    if self_chip_html and coll_chip_html:
        return f'<span class="rism-duo">{self_chip_html}<span class="rism-divider"></span>{coll_chip_html}</span>'
    return self_chip_html or coll_chip_html or ""

# =========================
# HEADER (logos fixed names)
# =========================
def build_header_html():
    def logo_img(filename, alt, cls):
        fp = OUT_DIR / "assets" / filename
        if not fp.exists():
            return ""
        return f'<img class="{cls}" src="assets/{html.escape(filename, quote=True)}" alt="{alt}">'

    hem_img = logo_img(HEM_LOGO, "HEM – Haute école de musique de Genève", "hem-logo")
    rism_img = logo_img(RISM_LOGO, "RISM", "rism-logo")

    hem_block = hem_img if hem_img else '<span class="logo-fallback">HEM</span>'
    rism_block = rism_img if rism_img else '<span class="logo-fallback logo-fallback--small">RISM</span>'

    return f"""
<header class="app-header">
  <div class="header-grid">
    <div class="left">
      <h1>ZinkNET</h1>
      <div class="tagline">Interactive catalogue for the Cornett Repertoire</div>
      <div class="meta-line">
        <strong>Project director:</strong> Lambert Colson · <strong>Research assistants:</strong> Tim Meulenbeld, Sushaant Jaccard
      </div>
    </div>

    <div class="right">
      {hem_block}
      <div class="collab-line">
        <span>In collaboration with</span>
        {rism_block}
      </div>
    </div>
  </div>
</header>
"""

# =========================
# CSS
# =========================
style_css = r"""
:root {
  --bg: #f4f5fb;
  --bg-soft: #ffffff;
  --accent: #234bb8;
  --accent-soft: rgba(35,75,184,0.06);
  --border-subtle: #d0d5eb;
  --border-strong: #b2b8dd;
  --text: #111827;
  --muted: #4b5563;
  --pill-border: #c3cff5;
  --green-collection: #1b5e3c;
  --green-collection-bg: #ddefe5;
  --tag-neutral-bg: #f5f5ff;
  --tag-neutral-border: #c5c8e6;

  --violet-border: #8b5cf6;
  --violet-bg: rgba(139,92,246,0.12);
  --violet-text: #4c1d95;
}
* { box-sizing:border-box; }
body {
  margin:0;
  font-family: Candara, system-ui, -apple-system, "Segoe UI", sans-serif;
  background: radial-gradient(circle at 0 0,#e7ecff 0,#f4f5fb 40%,#e5e9ff 100%);
  color: var(--text);
  line-height:1.45;
}
a { color: var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }

/* Header */
header.app-header {
  padding: 9px 22px 7px;
  border-bottom: 1px solid var(--border-subtle);
  background: linear-gradient(to right,rgba(255,255,255,0.98),rgba(245,247,255,0.96));
  position: sticky; top:0; z-index:20;
  backdrop-filter: blur(10px);
}
.header-grid{
  display:grid;
  grid-template-columns: minmax(0,1fr) auto;
  gap: 12px;
  align-items:start;
}
h1{
  margin:0;
  font-size: clamp(1.7rem, 3vw, 2.1rem);
  letter-spacing:-0.04em;
  font-weight:800;
  line-height:1.03;
}
.tagline{
  margin-top:2px;
  color:var(--muted);
  font-size:0.92rem;
}
.meta-line{
  margin-top:5px;
  color:var(--muted);
  font-size:0.86rem;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
  max-width: 100%;
}
.right{
  display:flex;
  flex-direction:column;
  align-items:flex-end;
  gap: 3px;
  padding-top: 1px;
}
.hem-logo,.rism-logo{
  display:block;
  width:auto;
  filter: drop-shadow(0 8px 18px rgba(15,23,42,0.10));
}
.hem-logo{ height: 58px; }  /* HEM larger only */
.rism-logo{ height: 30px; }

.collab-line{
  display:flex;
  align-items:center;
  gap: 8px;
  color:var(--muted);
  font-size:0.78rem;
  line-height:1.0;
  white-space:nowrap;
}
.logo-fallback{
  padding:6px 12px;
  border-radius:999px;
  border:1px solid var(--border-subtle);
  background:#fff;
  color:var(--muted);
  font-size:.84rem;
  font-weight:800;
  letter-spacing:.08em;
}
.logo-fallback--small{
  padding:5px 10px;
  font-size:.80rem;
}
@media (max-width: 980px){
  .header-grid{ grid-template-columns: 1fr; }
  .right{ align-items:flex-start; }
  .meta-line{ white-space:normal; }
}

/* Layout */
.shell { max-width:1400px; margin:0 auto; padding:16px 20px 26px; }
.layout { display:grid; grid-template-columns: minmax(260px,320px) minmax(0,1fr); gap:16px; }
@media (max-width: 960px) { .layout { grid-template-columns: 1fr; } }

.card {
  background: var(--bg-soft);
  border-radius:20px;
  padding:16px 16px 14px;
  border:1px solid var(--border-subtle);
  box-shadow:0 16px 40px rgba(15,23,42,0.08);
}
.card h2 {
  margin:0 0 10px;
  font-size:0.95rem;
  text-transform:uppercase;
  letter-spacing:.14em;
  font-weight:600;
  color:var(--muted);
}

.filters label {
  display:block; font-size:0.78rem;
  text-transform:uppercase; letter-spacing:.14em;
  color:var(--muted); margin-bottom:6px;
}
.filters input[type="text"], .filters input[type="number"] {
  width:100%; border-radius:999px;
  border:1px solid var(--border-subtle);
  background:#fafaff;
  padding:7px 11px;
  color:var(--text); font-size:0.9rem; outline:none;
}
.filters select {
  padding:7px 10px; border-radius:999px;
  border:1px solid var(--border-subtle);
  background:#fafaff;
  font-size:0.85rem; color:var(--text);
  outline:none; cursor:pointer;
}
.filters-row { display:flex; flex-direction:column; gap:10px; }
.filter-inline { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.filter-grid-2 { display:grid; grid-template-columns: 1fr 1fr; gap:8px; }

.entries { max-height: calc(100vh - 170px); overflow:auto; padding-right:4px; }

details.entry {
  border-radius:18px;
  padding:10px 11px 8px;
  margin-bottom:10px;
  background: linear-gradient(135deg,#ffffff,#f6f7ff);
  border:1.5px solid #c5c9ec;
  transition:border-color .15s ease, box-shadow .15s ease, transform .12s ease, background .15s ease;
  will-change: transform;
}
details.entry[open] {
  border-color:var(--border-strong);
  box-shadow:0 10px 26px rgba(15,23,42,0.14);
  transform: translateY(-1px);
  background:#ffffff;
}
summary { list-style:none; cursor:pointer; display:flex; align-items:center; justify-content:space-between; gap:8px; }
summary::-webkit-details-marker { display:none; }

.entry-main { display:flex; flex-direction:column; gap:3px; }
.entry-id { font-weight:650; font-size:0.96rem; color:#020617; }
.entry-composer { font-size:0.85rem; color:var(--muted); }
.entry-tags { display:flex; flex-wrap:wrap; gap:4px; margin-top:3px; align-items:center; }

.tag {
  font-size:0.7rem; padding:3px 7px; border-radius:999px;
  border:1px solid var(--tag-neutral-border);
  color:var(--muted); background:var(--tag-neutral-bg);
}
.tag-type { text-transform:uppercase; letter-spacing:.12em; border-color:#9db5ff; background:#e1e7ff; color:#1d3578; font-weight:650; }
.tag-source { text-transform:uppercase; letter-spacing:.12em; }
.tag-count { background: var(--green-collection-bg); border-color: var(--green-collection); color: var(--green-collection); font-weight:650; }
.tag-conc { border:1px solid var(--border-subtle); background:#ffffff; }

/* RISM mini-chip */
.tag-rism{
  border-color: var(--violet-border);
  background: var(--violet-bg);
  color: var(--violet-text);
  text-transform:uppercase;
  letter-spacing:.12em;
  font-weight:650;
}

/* Elegant duo wrapper */
.rism-duo{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:0;
  margin:0;
}
.rism-divider{
  width:1px;
  height:14px;
  background: rgba(76,29,149,0.35);
  border-radius:1px;
}

/* See RISM (violet, harmonized) */
.see-rism-tag {
  display:inline-flex; align-items:center; margin-left:6px;
  padding:2px 6px; border-radius:999px;
  border:1px solid var(--violet-border);
  background: var(--violet-bg);
  font-size:0.7rem; text-transform:uppercase; letter-spacing:.12em;
  color: var(--violet-text);
}

.entry-arrow { font-size:1.1rem; color:var(--muted); transition: transform .15s ease, color .15s ease; }
details[open] > summary .entry-arrow { transform: rotate(90deg); color:var(--accent); }

.entry-body { border-top:1px solid #dde1f7; margin-top:8px; padding-top:8px; font-size:0.9rem; }

dl.meta { margin:0; display:grid; grid-template-columns: minmax(0,150px) minmax(0,1fr); row-gap:4px; column-gap:12px; }
dt.meta-label { font-weight:600; color:var(--muted); font-size:0.8rem; }
dd.meta-value { margin:0; }

.instr-block { margin-top:8px; margin-bottom:8px; }
.instr-strip-uniform { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
.instr-pill {
  flex:0 1 470px;
  background:var(--accent-soft);
  border-radius:14px; padding:8px 11px;
  border:1px solid var(--pill-border);
  font-size:0.85rem;
}
.instr-pill.catalog-full {
  margin-top:8px; width:100%;
  background:#fdfdff;
  border-radius:14px; padding:8px 11px;
  border:1px solid var(--pill-border);
  font-size:0.85rem;
}
.instr-label {
  font-size:0.72rem; text-transform:uppercase; letter-spacing:0.12em;
  display:block; margin-bottom:3px; color:#25345f;
}
.instr-content { margin-top:2px; line-height:1.35; }

.subpieces {
  margin-top:8px; border-radius:14px;
  border:1px dashed var(--border-subtle);
  padding:7px 9px 7px; background:#f2f3ff;
}
.subpieces-title { font-size:0.78rem; text-transform:uppercase; letter-spacing:.13em; color:var(--muted); margin-bottom:4px; display:flex; gap:8px; align-items:center; }
.subpieces-matchcount{ font-size:.74rem; color:var(--violet-text); opacity:.85; }
.subpiece-line {
  padding:6px 0; border-top:1px solid #d8ddf5;
  font-size:0.88rem; display:flex; flex-direction:column; gap:2px;
}
.subpiece-line:first-of-type { border-top:none; }
.subpiece-line.match {
  border-top:1px solid rgba(139,92,246,0.35);
  background: rgba(139,92,246,0.07);
  border-radius:10px;
  padding-left:8px;
  padding-right:8px;
}
.subpiece-id { font-weight:600; color:#020617; }
.subpiece-meta { font-size:0.8rem; color:var(--muted); }
.subpiece-link { font-size:0.78rem; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.subpiece-conc-tag { margin-top:2px; }
.entry-open-link { margin-top:6px; font-size:0.8rem; }

.no-results {
  margin-top:10px; padding:10px 12px;
  border-radius:10px; border:1px solid var(--border-subtle);
  font-size:0.9rem; color:var(--muted);
}

/* Detail pages */
.detail-shell { max-width:900px; margin:0 auto; padding:18px 16px 28px; }
.detail-card {
  background:var(--bg-soft); border-radius:22px;
  border:1px solid var(--border-subtle);
  box-shadow:0 18px 45px rgba(15,23,42,0.12);
  padding:20px;
}
.detail-header { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; margin-bottom:10px; }
.detail-title { font-size:1.1rem; font-weight:650; margin:0; color:#020617; }
.detail-composer { margin:2px 0 0; font-size:0.9rem; color:var(--muted); }
.breadcrumbs { font-size:0.8rem; color:var(--muted); margin-bottom:10px; }
.detail-tags { display:flex; flex-wrap:wrap; gap:4px; justify-content:flex-end; align-items:center; }
.piece-meta { display:flex; flex-wrap:wrap; gap:12px 24px; font-size:0.9rem; margin:6px 0; }
.meta-block span.label { font-weight:600; font-size:0.8rem; color:var(--muted); display:block; }
.meta-block span.value { display:block; }
.piece-notes { font-size:0.88rem; margin-top:8px; }
.piece-notes .label { font-weight:600; color:var(--muted); display:block; margin-bottom:3px; }

/* Concordances cards */
.conc-block { margin-top:14px; }
.conc-heading { font-size:0.78rem; text-transform:uppercase; letter-spacing:.13em; color:var(--muted); margin-bottom:6px; }
.conc-cards { display:flex; flex-direction:column; gap:6px; }
.conc-card {
  border-radius:14px; border:1px solid var(--border-subtle);
  background:#ffffff; padding:7px 9px;
  display:flex; gap:8px; align-items:flex-start; font-size:0.85rem;
}
.conc-id-link {
  font-weight:600; padding:3px 8px; border-radius:999px;
  border:1px solid var(--accent); background:var(--accent-soft);
  white-space:nowrap;
}
.conc-main { flex:1; min-width:0; }
.conc-title { font-weight:500; color:#020617; }
.conc-composer { font-size:0.78rem; color:var(--muted); }
.conc-tags { margin-top:2px; display:flex; flex-wrap:wrap; gap:4px; align-items:center; }

.detail-subpieces { margin-top:16px; }
.sub-entry {
  border-radius:16px; border:1px solid var(--border-subtle);
  background:#f6f7ff; padding:8px 9px; margin-bottom:6px;
}
.sub-entry summary { padding:0; cursor:pointer; }
.sub-entry-header { display:flex; flex-direction:column; gap:2px; }
.sub-entry-title { font-size:0.9rem; font-weight:600; color:#020617; }
.sub-entry-composer { font-size:0.8rem; color:var(--muted); }
.sub-entry-body { border-top:1px solid #dde1f0; margin-top:6px; padding-top:6px; font-size:0.85rem; }
.sub-entry-body .instr-pill, .sub-entry-body .instr-pill.catalog-full { background:#ffffff; border-style:dashed; }
.sub-entry-conc { margin-top:4px; }

/* NEW: RISM drawer on detail pages (variant B) */
details.rism {
  margin-top:14px;
  border:1.5px solid rgba(139,92,246,0.35);
  background: linear-gradient(180deg, rgba(139,92,246,0.08), rgba(255,255,255,0.95));
  border-radius:18px;
  padding: 10px 12px;
}
details.rism > summary{
  cursor:pointer;
  list-style:none;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
}
details.rism > summary::-webkit-details-marker{display:none}
.rism-left{display:flex; align-items:center; gap:8px; flex-wrap:wrap;}
.rism-title{
  font-size:.78rem; text-transform:uppercase; letter-spacing:.14em;
  color:var(--violet-text);
  font-weight:800;
}
.rism-mini{display:flex; gap:6px; flex-wrap:wrap; align-items:center;}
.rism-mini .pill{
  font-size:.74rem;
  padding:2px 8px;
  border-radius:999px;
  border:1px solid rgba(139,92,246,0.45);
  background: rgba(139,92,246,0.10);
  color: var(--violet-text);
  white-space:nowrap;
}
.rism-body{
  margin-top:10px;
  border-top:1px solid rgba(139,92,246,0.22);
  padding-top:10px;
  display:grid;
  grid-template-columns: minmax(0,1fr);
  gap:10px;
}
.rism-kv{
  display:grid;
  grid-template-columns: minmax(0,140px) minmax(0,1fr);
  gap:6px 10px;
  font-size:.88rem;
}
.rism-kv .k{color:var(--muted); font-weight:600; font-size:.80rem}
.rism-kv .v{color:#111827}
.rism-holdings{
  margin:0; padding-left:16px;
  font-size:.88rem; line-height:1.35;
  max-height: 260px; overflow:auto;
}
.rism-hint{font-size:.80rem; color:var(--muted);}
"""

# =========================
# BUILDERS
# =========================
def build_instr_block_for_record(rec, include_catalogs):
    uniform_bits = []
    if rec["instr_rism_main_raw"]:
        fm = format_uniform_instr(rec["instr_rism_main_raw"], alternative=False)
        if fm:
            uniform_bits.append(f'<div class="instr-pill">{fm}</div>')
    if rec["instr_rism_alt_raw"]:
        fa = format_uniform_instr(rec["instr_rism_alt_raw"], alternative=True)
        if fa:
            uniform_bits.append(f'<div class="instr-pill">{fa}</div>')

    parts = []
    if uniform_bits:
        parts.append(f'<div class="instr-strip-uniform">{"".join(uniform_bits)}</div>')
    if include_catalogs and rec["instr_catalogs"]:
        parts.append(
            f'<div class="instr-pill catalog-full">'
            f'<strong class="instr-label">INSTRUMENTATION (CATALOGUES)</strong>'
            f'<div class="instr-content">{rec["instr_catalogs"]}</div></div>'
        )
    return f'<div class="instr-block">{"".join(parts)}</div>' if parts else ""

def holdings_lines(txt):
    txt = clean_str(txt)
    if not txt:
        return []
    # split on newline, ignore empties
    return [ln.strip() for ln in re.split(r"\r?\n", txt) if ln.strip()]

def holdings_list_html(txt):
    lines = holdings_lines(txt)
    if not lines:
        return ""
    lis = "".join(f"<li>{html.escape(ln, quote=False)}</li>" for ln in lines)
    return f'<ul class="rism-holdings">{lis}</ul>'

def unique_nonempty(seq):
    out = []
    seen = set()
    for x in seq:
        x = clean_str(x)
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

# =========================
# TEMPLATES
# =========================
index_template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ZinkNET — Interactive catalogue</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="style.css">
</head>
<body>
@@HEADER@@
<main class="shell">
  <div class="layout">
    <section class="card">
      <h2>Search & filters</h2>
      <div class="filters">
        <div class="filters-row">
          <div>
            <label for="searchInput">Global search</label>
            <input id="searchInput" type="text" placeholder="Composer, title, number, library…" />
          </div>

          <div>
            <label for="instrInput">Search in instrumentations</label>
            <input id="instrInput" type="text" placeholder="e.g. cnto, cornettino, trb…" />
          </div>

          <!-- NEW: RISM chronology filter (Earliest/Latest used internally, not displayed) -->
          <div>
            <label>RISM chronology</label>
            <div class="filter-grid-2">
              <input id="yearFrom" type="number" inputmode="numeric" placeholder="From (e.g. 1650)" />
              <input id="yearTo" type="number" inputmode="numeric" placeholder="To (e.g. 1750)" />
            </div>
          </div>

          <!-- Search Tool builder -->
          <div>
            <label>Instrumentation Search Builder</label>
            <div class="filter-inline" style="gap:6px;">
              <select id="stMode">
                <option value="include">Include</option>
                <option value="exclude">Exclude</option>
              </select>

              <!-- NEW: exact vs ≥ -->
              <select id="stCmp">
                <option value="gte">≥</option>
                <option value="eq">=</option>
              </select>

              <select id="stInstr">
                <option value="">Select instrument…</option>
              </select>
              <select id="stQty">
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="4">4</option>
                <option value="5">5</option>
                <option value="6">6</option>
                <option value="7">7</option>
                <option value="8">8</option>
                <option value="9">9</option>
                <option value="10">10</option>
              </select>
              <button id="stAdd" type="button" class="tag" style="cursor:pointer;">Add</button>
              <button id="stClear" type="button" class="tag" style="cursor:pointer;">Clear</button>
            </div>
            <div id="stActive" style="margin-top:8px; display:flex; flex-wrap:wrap; gap:6px;"></div>
          </div>

          <div>
            <label>Music type & source</label>
            <div class="filter-inline">
              <select id="musicFilter"><option value="">All music types</option></select>
              <select id="sourceFilter"><option value="">All sources</option></select>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>Catalogue</h2>
      <div id="entries" class="entries">
@@ENTRIES@@
      </div>
      <div id="noResults" class="no-results" style="display:none;">
        No results for these filters.
      </div>
    </section>
  </div>
</main>

<script>
  const searchInput = document.getElementById('searchInput');
  const instrInput = document.getElementById('instrInput');
  const yearFrom = document.getElementById('yearFrom');
  const yearTo = document.getElementById('yearTo');
  const musicFilter = document.getElementById('musicFilter');
  const sourceFilter = document.getElementById('sourceFilter');
  const entriesContainer = document.getElementById('entries');
  const cards = Array.from(entriesContainer.querySelectorAll('.entry'));
  const noResults = document.getElementById('noResults');
  function normalize(s){ return (s || '').toLowerCase(); }

  function parseIntSafe(x){
    const n = parseInt(x, 10);
    return Number.isFinite(n) ? n : null;
  }

  // -------------------------
  // Search Tool controls
  // -------------------------
  const stMode  = document.getElementById('stMode');
  const stCmp   = document.getElementById('stCmp');
  const stInstr = document.getElementById('stInstr');
  const stQty   = document.getElementById('stQty');
  const stAdd   = document.getElementById('stAdd');
  const stClear = document.getElementById('stClear');
  const stActive = document.getElementById('stActive');

  // injected by Python: [{k:"cnto", n:123}, ...]
  const SEARCH_TOOL_INSTRS = @@SEARCH_TOOL_INSTRS@@;
  const stRules = []; // {mode:"include"|"exclude", cmp:"gte"|"eq", k:"cnto", n:3}

  SEARCH_TOOL_INSTRS.forEach(o => {
    const opt = document.createElement('option');
    opt.value = o.k;
    opt.textContent = `${o.k} (${o.n})`;
    stInstr.appendChild(opt);
  });

  function renderStRules(){
    stActive.innerHTML = '';
    stRules.forEach((r, idx) => {
      const chip = document.createElement('span');
      chip.className = 'tag tag-conc';
      chip.style.cursor = 'pointer';
      const sign = r.mode === 'include' ? '+' : '–';
      const cmp = (r.cmp === 'eq') ? '=' : '≥';
      chip.textContent = `${sign} ${r.k} ${cmp} ${r.n}  ×`;
      chip.title = 'Click to remove';
      chip.addEventListener('click', () => {
        stRules.splice(idx, 1);
        renderStRules();
        applyFilters();
      });
      stActive.appendChild(chip);
    });
  }

  stAdd.addEventListener('click', () => {
    const k = stInstr.value;
    const n = parseInt(stQty.value || '1', 10);
    const mode = stMode.value;
    const cmp = stCmp.value;
    if(!k) return;
    stRules.push({mode, cmp, k, n});
    renderStRules();
    applyFilters();
  });

  stClear.addEventListener('click', () => {
    stRules.length = 0;
    renderStRules();
    applyFilters();
  });

  // -------------------------
  // Cache parsers per card
  // -------------------------
  function parseSearchToolPieces(card){
    if(card.__stPieces) return card.__stPieces;

    const raw = card.dataset.stoolPieces || '';
    const pieces = [];
    if(raw){
      // format: pid@@sc1||sc2##pid@@sc1||...
      raw.split('##').forEach(chunk => {
        if(!chunk) return;
        const parts = chunk.split('@@');
        if(parts.length !== 2) return;
        const pid = parts[0];
        const scRaw = parts[1] || '';
        const scenarios = [];

        scRaw.split('||').forEach(scStr => {
          if(!scStr) return;
          const sc = {};
          scStr.split('|').forEach(pair => {
            const kv = pair.split('=');
            if(kv.length !== 2) return;
            const k = kv[0];
            const v = kv[1];
            if(k && v) sc[k] = parseInt(v, 10) || 0;
          });
          scenarios.push(sc);
        });

        pieces.push({pid, scenarios});
      });
    }
    card.__stPieces = pieces;
    return pieces;
  }

  function parseYearRangesPieces(card){
    if(card.__yrPieces) return card.__yrPieces;

    const raw = card.dataset.yrPieces || '';
    const pieces = [];
    if(raw){
      // format: pid@@min:max||min:max##pid@@...
      raw.split('##').forEach(chunk => {
        if(!chunk) return;
        const parts = chunk.split('@@');
        if(parts.length !== 2) return;
        const pid = parts[0];
        const rangesRaw = parts[1] || '';
        const ranges = [];

        rangesRaw.split('||').forEach(r => {
          if(!r) return;
          const mm = r.split(':');
          if(mm.length !== 2) return;
          const a = parseIntSafe(mm[0]);
          const b = parseIntSafe(mm[1]);
          if(a !== null && b !== null) ranges.push([a,b]);
        });

        pieces.push({pid, ranges});
      });
    }
    card.__yrPieces = pieces;
    return pieces;
  }

  // -------------------------
  // Matching logic
  // -------------------------
  function ruleOk(val, rule){
    const n = rule.n;
    const cmp = rule.cmp;
    if(rule.mode === 'include'){
      if(cmp === 'eq') return (val === n);
      return (val >= n);
    } else { // exclude
      if(cmp === 'eq') return (val !== n);
      return (val < n);
    }
  }

  // Returns {ok:boolean, matchPids:Set}
  function matchesSearchTool(card){
    if(!stRules.length) return {ok:true, matchPids:new Set()};
    const pieces = parseSearchToolPieces(card);
    if(!pieces.length) return {ok:false, matchPids:new Set()};

    const matchPids = new Set();

    for(const p of pieces){
      const scs = p.scenarios || [];
      if(!scs.length) continue;

      const okPiece = scs.some(sc => {
        for(const r of stRules){
          const val = sc[r.k] || 0;
          if(!ruleOk(val, r)) return false;
        }
        return true;
      });

      if(okPiece){
        matchPids.add(p.pid);
      }
    }

    return {ok: matchPids.size > 0, matchPids};
  }

  function overlapsYearRange(rmin, rmax, fromY, toY){
    if(fromY !== null && rmax < fromY) return false;
    if(toY   !== null && rmin > toY)   return false;
    return true;
  }

  // Returns {ok:boolean, matchPids:Set}
  function matchesYearFilter(card){
    const fromY = parseIntSafe(yearFrom.value);
    const toY   = parseIntSafe(yearTo.value);
    if(fromY === null && toY === null) return {ok:true, matchPids:new Set()};

    const pieces = parseYearRangesPieces(card);
    if(!pieces.length) return {ok:false, matchPids:new Set()};

    const matchPids = new Set();

    for(const p of pieces){
      const ranges = p.ranges || [];
      if(!ranges.length) continue;

      const okPiece = ranges.some(([a,b]) => overlapsYearRange(a,b, fromY, toY));
      if(okPiece) matchPids.add(p.pid);
    }

    return {ok: matchPids.size > 0, matchPids};
  }

  function applyHighlight(card, matchPids){
    // highlight lines in collections (subpieces)
    const lines = card.querySelectorAll('.subpiece-line[data-pid]');
    if(!lines.length) return;

    let count = 0;
    lines.forEach(ln => {
      const pid = ln.dataset.pid || '';
      const hit = matchPids && matchPids.has(pid);
      ln.classList.toggle('match', !!hit);
      if(hit) count++;
    });

    const badge = card.querySelector('.subpieces-matchcount');
    if(badge){
      if(matchPids && matchPids.size){
        badge.textContent = `• ${count} match${count===1?'':'es'}`;
      } else {
        badge.textContent = '';
      }
    }
  }

  // -------------------------
  // Dropdown sets for music/source
  // -------------------------
  const musicSet = new Set();
  const sourceSet = new Set();
  cards.forEach(card => {
    (card.dataset.musicTypes || '').split('||').filter(Boolean).forEach(v => musicSet.add(v));
    (card.dataset.sourceTypes || '').split('||').filter(Boolean).forEach(v => sourceSet.add(v));
  });
  Array.from(musicSet).sort().forEach(v => {
    const o=document.createElement('option'); o.value=v; o.textContent=v; musicFilter.appendChild(o);
  });
  Array.from(sourceSet).sort().forEach(v => {
    const o=document.createElement('option'); o.value=v; o.textContent=v; sourceFilter.appendChild(o);
  });

  // -------------------------
  // Main filter
  // -------------------------
  function applyFilters() {
    const q  = normalize(searchInput.value);
    const qi = normalize(instrInput.value);
    const mt = musicFilter.value;
    const st = sourceFilter.value;
    let visible = 0;

    cards.forEach(card => {
      const text  = normalize(card.dataset.search);
      const instr = normalize(card.dataset.instr);
      const mts = (card.dataset.musicTypes || '').split('||').filter(Boolean);
      const sts = (card.dataset.sourceTypes || '').split('||').filter(Boolean);

      let ok = true;
      if (q  && !text.includes(q)) ok = false;
      if (qi && !instr.includes(qi)) ok = false;
      if (mt && !mts.includes(mt)) ok = false;
      if (st && !sts.includes(st)) ok = false;

      // Search Tool (collection intelligent)
      let stMatch = {ok:true, matchPids:new Set()};
      if(ok){
        stMatch = matchesSearchTool(card);
        if(!stMatch.ok) ok = false;
      }

      // Year filter (collection intelligent)
      let yrMatch = {ok:true, matchPids:new Set()};
      if(ok){
        yrMatch = matchesYearFilter(card);
        if(!yrMatch.ok) ok = false;
      }

      // Apply highlight: intersection of matches when both filters active
      // If only one active, use that set. If none active, clear.
      const stActiveOn = stRules.length > 0;
      const yrActiveOn = (parseIntSafe(yearFrom.value) !== null) || (parseIntSafe(yearTo.value) !== null);

      let highlightSet = null;
      if(stActiveOn && yrActiveOn){
        highlightSet = new Set();
        stMatch.matchPids.forEach(pid => { if(yrMatch.matchPids.has(pid)) highlightSet.add(pid); });
      } else if(stActiveOn){
        highlightSet = stMatch.matchPids;
      } else if(yrActiveOn){
        highlightSet = yrMatch.matchPids;
      } else {
        highlightSet = new Set();
      }

      card.style.display = ok ? '' : 'none';
      if (ok) visible++;

      applyHighlight(card, highlightSet);
    });

    noResults.style.display = visible ? 'none' : '';
  }

  searchInput.addEventListener('input', applyFilters);
  instrInput.addEventListener('input', applyFilters);
  yearFrom.addEventListener('input', applyFilters);
  yearTo.addEventListener('input', applyFilters);
  musicFilter.addEventListener('change', applyFilters);
  sourceFilter.addEventListener('change', applyFilters);
</script>
</body>
</html>
"""

detail_template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>@@TITLE_FULL@@</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="style.css">
</head>
<body>
@@HEADER@@
<main class="detail-shell">
  <div class="breadcrumbs"><a href="index.html">ZinkNET index</a>@@BREADCRUMB@@</div>
  @@PARENT_BTN@@
  <article class="detail-card">
    <div class="detail-header">
      <div>
        <p class="detail-title">@@ID@@ — @@TITLE@@</p>
        <p class="detail-composer">@@COMPOSER@@</p>
      </div>
      <div class="detail-tags">@@TAGS@@</div>
    </div>

    @@INSTR@@
    <div class="piece-meta">@@META@@</div>
    @@RISM_DRAWER@@
    @@BIBLIO@@
    @@NOTE@@
    @@ORG@@
    @@CONC@@
    @@SUBPIECES@@
  </article>
</main>
</body>
</html>
"""

# =========================
# MAIN
# =========================
def main():
    # Clean output dir
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Force fully static on GitHub Pages
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # Write CSS
    (OUT_DIR / "style.css").write_text(style_css, encoding="utf-8")

    # Copy assets
    assets_dir = OUT_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if (ASSETS_SRC / HEM_LOGO).exists():
        shutil.copy(ASSETS_SRC / HEM_LOGO, assets_dir / HEM_LOGO)
    if (ASSETS_SRC / RISM_LOGO).exists():
        shutil.copy(ASSETS_SRC / RISM_LOGO, assets_dir / RISM_LOGO)

    # Read Google Sheet CSV
    df = pd.read_csv(SHEET_CSV_URL, dtype={"RISM No.": "string"})
    df.columns = [str(c).replace("\r\n", "\n").strip() for c in df.columns]

    df["__sort_key"] = df["ZINKNET NO."].apply(parse_zinknet)
    df["__group"] = df["ZINKNET NO."].apply(group_id)
    df_sorted = df.sort_values("__sort_key").reset_index(drop=True)

    # Groups
    groups = {}
    for _, row in df_sorted.iterrows():
        zid = clean_str(get_col(row, "ZINKNET NO."))
        if not zid:
            continue
        gid = row["__group"]
        groups.setdefault(gid, []).append(zid)
    for gid, ids in groups.items():
        ids.sort(key=parse_zinknet)
    group_sizes = {gid: len(ids) for gid, ids in groups.items()}

    # Records
    records = {}
    for _, row in df_sorted.iterrows():
        zid = clean_str(get_col(row, "ZINKNET NO."))
        if not zid:
            continue

        gid = row["__group"]
        gcount = group_sizes.get(gid, 1)

        rec = {
            "id": zid,
            "group": gid,
            "group_count": int(gcount),
            "indiv_coll": clean_str(get_col(row, "Indiv. or Coll.")),
            "composer_raw": clean_str(get_col(row, "Composer")),
            "title_raw": clean_str(get_col(row, "Title")),
            "concordances_raw": clean_str(get_col(row, "Concordances")),
            "instr_rism_main_raw": clean_str(get_col(row, "Instrumentation principal\nRISM extended")),
            "instr_rism_alt_raw": clean_str(get_col(row, "Instrumentation alternative\nRISM extended")),
            "instr_catalogs_raw": clean_str(get_col(row, "Instrumentation from Catalogs")),
            "music_type_raw": norm_music_type(get_col(row, "Music type")),
            "source_type_raw": clean_str(get_col(row, "Source type")),
            "rism_no_raw": clean_numberish(get_col(row, "RISM No.")),
            "rism_link_raw": clean_str(get_col(row, "RISM link")),
            "category_raw": clean_str(get_col(row, "Category")),
            "note_raw": clean_str(get_col(row, "Note")),
            "bibliography_raw": clean_str(get_col(row, "Bibliography")),
            "organology_raw": clean_str(get_col(row, "Organology")),
            # Search Tool
            "search_tool_raw": clean_str(get_col(row, "Search Tool")),
            # NEW: RISM text fields (no API needed)
            "rism_holdings_raw": clean_str(get_col(row, "RISM Holdings")),
            "rism_date_raw": clean_str(get_col(row, "RISM Date")),
            # NEW: RISM numeric bounds (filter only, not displayed)
            "rism_earliest_year_raw": clean_numberish(get_col(row, "RISM Earliest Year")),
            "rism_latest_year_raw": clean_numberish(get_col(row, "RISM Latest Year")),
        }

        lib_raw = get_col(row, "Library-ies (public)")
        shelf_raw = get_col(row, "Shelfmark (public)")
        lib_clean, flag_lib = strip_see_rism(lib_raw)
        shelf_clean, flag_shelf = strip_see_rism(shelf_raw)
        rec["library_raw"] = lib_clean
        rec["shelfmark_raw"] = shelf_clean
        rec["see_rism"] = flag_lib or flag_shelf

        rec["composer"] = escape_textnode(rec["composer_raw"])
        rec["title"] = escape_textnode(rec["title_raw"])
        rec["instr_catalogs"] = escape_with_italics(rec["instr_catalogs_raw"])
        rec["bibliography"] = escape_with_italics(rec["bibliography_raw"])
        rec["music_type"] = escape_textnode(rec["music_type_raw"])
        rec["source_type"] = escape_textnode(rec["source_type_raw"])
        rec["library"] = escape_textnode(rec["library_raw"])
        rec["shelfmark"] = escape_textnode(rec["shelfmark_raw"])
        rec["category"] = escape_textnode(rec["category_raw"])
        rec["note"] = escape_textnode(rec["note_raw"])
        rec["organology"] = escape_textnode(rec["organology_raw"])

        # Search Tool scenarios
        rec["search_scenarios"] = parse_search_tool_to_scenarios(rec["search_tool_raw"], limit=256)

        # Years parsed (filter only)
        rec["year_min"] = parse_int_safe(rec["rism_earliest_year_raw"])
        rec["year_max"] = parse_int_safe(rec["rism_latest_year_raw"])

        records[zid] = rec

    # concordances ids
    for rec in records.values():
        rec["concordances_ids"] = [cid for cid in parse_conc_ids(rec["concordances_raw"]) if cid in records]

    # virtual collections
    virtual_headers = set()
    for gid, ids in groups.items():
        has_real_coll = any(records[z]["indiv_coll"] == "Coll." for z in ids if z in records)
        if (not has_real_coll) and len(ids) > 1:
            virtual_headers.add(gid)
            lib = next((records[z]["library_raw"] for z in ids if records.get(z, {}).get("library_raw")), "")
            shelf = next((records[z]["shelfmark_raw"] for z in ids if records.get(z, {}).get("shelfmark_raw")), "")
            title_label = " ".join([x for x in [lib, shelf] if x]).strip()
            records[gid] = {
                "id": gid, "group": gid, "group_count": len(ids), "indiv_coll": "VirtualColl",
                "composer_raw": "", "title_raw": title_label, "concordances_raw": "",
                "instr_rism_main_raw": "", "instr_rism_alt_raw": "", "instr_catalogs_raw": "",
                "music_type_raw": "", "source_type_raw": "",
                "rism_no_raw": "", "rism_link_raw": "",
                "library_raw": lib, "shelfmark_raw": shelf, "see_rism": False,
                "category_raw": "", "note_raw": "", "bibliography_raw": "", "organology_raw": "",
                "composer": "", "title": escape_textnode(title_label),
                "instr_catalogs": "", "bibliography": "",
                "music_type": "", "source_type": "",
                "library": escape_textnode(lib), "shelfmark": escape_textnode(shelf),
                "category": "", "note": "", "organology": "",
                "concordances_ids": [],
                "search_tool_raw": "",
                "search_scenarios": [],
                "rism_holdings_raw": "",
                "rism_date_raw": "",
                "rism_earliest_year_raw": "",
                "rism_latest_year_raw": "",
                "year_min": None,
                "year_max": None,
            }

    # Build global instrument index + frequency (pieces where it can appear)
    all_instr = set()
    instr_freq = {}
    for rec in records.values():
        scs = rec.get("search_scenarios") or []
        present = set()
        for sc in scs:
            for k in sc.keys():
                all_instr.add(k)
                present.add(k)
        for k in present:
            instr_freq[k] = instr_freq.get(k, 0) + 1
    all_instr_sorted = sorted(all_instr, key=lambda x: x.lower())
    search_tool_js = json.dumps(
        [{"k": k, "n": int(instr_freq.get(k, 0))} for k in all_instr_sorted],
        ensure_ascii=False
    )

    # =========================
    # INDEX BUILD
    # =========================
    group_html_parts = []
    sorted_group_ids = sorted(groups.keys(), key=lambda g: parse_zinknet(g))

    for gid in sorted_group_ids:
        ids = groups[gid]
        coll_id = next((z for z in ids if records.get(z, {}).get("indiv_coll") == "Coll."), None)
        is_virtual_collection = gid in virtual_headers

        header_id = coll_id if coll_id else (gid if is_virtual_collection else ids[0])
        hrec = records[header_id]
        gcount_total = len(ids)

        # tags (dedupe only inside this tag-row)
        used_links_tags = set()
        tags_html = []

        if hrec["music_type_raw"]:
            tags_html.append(f'<span class="tag tag-type">{escape_textnode(hrec["music_type_raw"])}</span>')
        if hrec["source_type_raw"]:
            tags_html.append(f'<span class="tag tag-source">{escape_textnode(hrec["source_type_raw"])}</span>')

        if coll_id or is_virtual_collection:
            nb_pieces = gcount_total - 1 if coll_id else gcount_total
            nb_pieces = max(nb_pieces, 0)
            tags_html.append(f'<span class="tag tag-count">{nb_pieces} piece{"s" if nb_pieces != 1 else ""}</span>')

        if hrec["concordances_ids"]:
            n = len(hrec["concordances_ids"])
            tags_html.append(f'<span class="tag tag-conc">{n} concordance{"s" if n!=1 else ""}</span>')

        # NEW: RISM date chip on index
        rism_dates = unique_nonempty(records[z].get("rism_date_raw", "") for z in ids if z in records)
        if not is_virtual_collection:
            if len(rism_dates) == 1:
                tags_html.append(f'<span class="tag tag-rism">RISM date: {escape_textnode(rism_dates[0])}</span>')
            elif len(rism_dates) > 1:
                tags_html.append(f'<span class="tag tag-rism">RISM date: multiple</span>')

        if not is_virtual_collection:
            chip = rism_chip_self(hrec, used_links_tags)
            if chip:
                tags_html.append(chip)

        display_id = header_id.split("/", 1)[0] if (coll_id and "/" in header_id) else header_id

        # Collections: no catalog instrumentation in main view
        instr_block = build_instr_block_for_record(hrec, include_catalogs=not (coll_id or is_virtual_collection))

        meta_rows = []
        if (not is_virtual_collection) and hrec["composer"]:
            meta_rows.append(f'<dt class="meta-label">Composer</dt><dd class="meta-value">{hrec["composer"]}</dd>')

        lib_val = hrec["library"]
        shelf_val = hrec["shelfmark"]
        if hrec["see_rism"]:
            if lib_val: lib_val += " "
            lib_val += '<span class="see-rism-tag">See RISM</span>'
            if shelf_val: shelf_val += " "
            shelf_val += '<span class="see-rism-tag">See RISM</span>'

        if lib_val:
            meta_rows.append(f'<dt class="meta-label">Library</dt><dd class="meta-value">{lib_val}</dd>')
        if shelf_val:
            meta_rows.append(f'<dt class="meta-label">Shelfmark</dt><dd class="meta-value">{shelf_val}</dd>')

        meta_html = ('<dl class="meta">' + "\n".join(meta_rows) + "</dl>") if meta_rows else ""

        # contents
        sub_block = ""
        if coll_id or is_virtual_collection:
            sub_lines = []
            for pid in ids:
                if coll_id and pid == coll_id:
                    continue
                r = records[pid]

                conc_tag = ""
                if r["concordances_ids"]:
                    n = len(r["concordances_ids"])
                    conc_tag = f'<div class="subpiece-conc-tag"><span class="tag tag-conc">{n} concordance{"s" if n!=1 else ""}</span></div>'

                instr_short = r["instr_rism_main_raw"] or r["instr_catalogs_raw"]
                instr_short_disp = escape_textnode(instr_short) if instr_short else ""

                used_links_line = set()
                sub_rism = rism_chip_self(r, used_links_line)

                # NEW: add data-pid for highlight
                sub_lines.append(f"""
      <div class="subpiece-line" data-pid="{escape_attr(pid)}">
        <div><span class="subpiece-id">{escape_textnode(pid)} — {r['title'] or '(Untitled)'}</span></div>
        <div class="subpiece-meta">{r['composer'] or ''}</div>
        <div class="subpiece-meta">{instr_short_disp}</div>
        <div class="subpiece-meta subpiece-link">
          <a href="piece-{pid.replace('/','-')}.html" target="_blank" rel="noopener">Open piece page</a>
          {sub_rism}
        </div>
        {conc_tag}
      </div>""")
            if sub_lines:
                sub_block = f"""
      <div class="subpieces">
        <div class="subpieces-title">Contents <span class="subpieces-matchcount"></span></div>
        {''.join(sub_lines)}
      </div>"""

        title_html = hrec["title"] if hrec["title"] else ("" if is_virtual_collection else "<em>(Untitled)</em>")
        title_part = f" — {title_html}" if title_html else ""

        # dataset attributes for filtering (full text)
        search_blob_parts = []
        for z in ids:
            rr = records[z]
            search_blob_parts.extend([
                z, rr["composer_raw"], rr["title_raw"],
                rr["instr_rism_main_raw"], rr["instr_rism_alt_raw"], rr["instr_catalogs_raw"],
                rr["library_raw"], rr["shelfmark_raw"],
                rr["music_type_raw"], rr["source_type_raw"],
                rr["note_raw"], rr["organology_raw"],
                # NEW: RISM text fields indexable
                rr.get("rism_date_raw",""),
                rr.get("rism_holdings_raw",""),
            ])
        search_blob = " ".join([p for p in search_blob_parts if p]).replace("\n", " ")
        music_types_set = sorted({records[z]["music_type_raw"] for z in ids if records[z]["music_type_raw"]})
        source_types_set = sorted({records[z]["source_type_raw"] for z in ids if records[z]["source_type_raw"]})
        instr_blob = " ".join(
            ((records[z]["instr_rism_main_raw"] + " " + records[z]["instr_rism_alt_raw"] + " " + records[z]["instr_catalogs_raw"]).strip())
            for z in ids
        ).replace("\n", " ")

        # Search Tool scenarios per piece (collection intelligent)
        # format: pid@@sc1||sc2##pid@@...
        piece_chunks = []
        for z in ids:
            rr = records[z]
            scs = rr.get("search_scenarios") or []
            sc_keys = []
            seen_sc = set()
            for sc in scs:
                key = "|".join(f"{k}={v}" for k, v in sorted(sc.items()))
                if key and key not in seen_sc:
                    seen_sc.add(key)
                    sc_keys.append(key)
            piece_chunks.append(f"{z}@@{'||'.join(sc_keys)}")
        stool_pieces_blob = "##".join(piece_chunks)

        # Year ranges per piece (collection intelligent)
        # format: pid@@min:max||min:max##pid@@...
        yr_chunks = []
        for z in ids:
            rr = records[z]
            ymin = rr.get("year_min", None)
            ymax = rr.get("year_max", None)
            if ymin is None or ymax is None:
                yr_chunks.append(f"{z}@@")
            else:
                yr_chunks.append(f"{z}@@{ymin}:{ymax}")
        yr_pieces_blob = "##".join(yr_chunks)

        open_link_html = f'<div class="entry-open-link"><a href="piece-{header_id.replace("/","-")}.html" target="_blank" rel="noopener">Open detailed page</a></div>'

        group_html_parts.append(f"""
    <details class="entry"
      data-search="{escape_attr(search_blob)}"
      data-music-types="{escape_attr('||'.join(music_types_set))}"
      data-source-types="{escape_attr('||'.join(source_types_set))}"
      data-instr="{escape_attr(instr_blob)}"
      data-stool-pieces="{escape_attr(stool_pieces_blob)}"
      data-yr-pieces="{escape_attr(yr_pieces_blob)}">
      <summary>
        <div class="entry-main">
          <div class="entry-id">{escape_textnode(display_id)}{title_part}</div>
          <div class="entry-composer">{hrec['composer'] or ''}</div>
          <div class="entry-tags">{''.join(tags_html)}</div>
        </div>
        <div class="entry-arrow">›</div>
      </summary>
      <div class="entry-body">
        {instr_block}
        {meta_html}
        {sub_block}
        {open_link_html}
      </div>
    </details>
    """)

    entries_html = "\n".join(group_html_parts)

    (OUT_DIR / "index.html").write_text(
        index_template
        .replace("@@HEADER@@", build_header_html())
        .replace("@@ENTRIES@@", entries_html)
        .replace("@@SEARCH_TOOL_INSTRS@@", search_tool_js),
        encoding="utf-8"
    )

    # =========================
    # DETAIL PAGES
    # =========================
    for zid, rec in records.items():
        used_links_page = set()  # no duplicate RISM link anywhere on the page

        gid = rec["group"]
        ids_in_group = groups.get(gid, [zid])
        coll_id = next((x for x in ids_in_group if records.get(x, {}).get("indiv_coll") == "Coll."), None)
        is_virtual_group = gid in virtual_headers

        parent_id = coll_id if coll_id else (gid if is_virtual_group else "")
        parent_rec = records.get(parent_id) if parent_id else None

        breadcrumb_extra = ""
        parent_btn = ""
        if parent_id and zid != parent_id:
            breadcrumb_extra = f' &nbsp;›&nbsp; <a href="piece-{parent_id.replace("/","-")}.html" target="_blank" rel="noopener">Collection {escape_textnode(parent_id)}</a>'
            parent_btn = f'<div style="margin:8px 0 12px;"><a class="tag tag-count" href="piece-{parent_id.replace("/","-")}.html" target="_blank" rel="noopener">Open collection</a></div>'

        # Tags: type/source + concordances + (RISM date) + (RISM self + collection)
        tags = []
        if rec["music_type_raw"]:
            tags.append(f'<span class="tag tag-type">{escape_textnode(rec["music_type_raw"])}</span>')
        if rec["source_type_raw"]:
            tags.append(f'<span class="tag tag-source">{escape_textnode(rec["source_type_raw"])}</span>')
        if rec["concordances_ids"]:
            n = len(rec["concordances_ids"])
            tags.append(f'<span class="tag tag-conc">{n} concordance{"s" if n!=1 else ""}</span>')

        # NEW: RISM date chip (editorial text)
        if rec.get("rism_date_raw",""):
            tags.append(f'<span class="tag tag-rism">RISM date: {escape_textnode(rec["rism_date_raw"])}</span>')

        self_link = norm_url(rec.get("rism_link_raw",""))
        coll_link = norm_url(parent_rec.get("rism_link_raw","")) if parent_rec else ""

        self_chip = rism_chip_self(rec, used_links_page)
        coll_chip = ""
        if parent_rec and coll_link and (coll_link != self_link) and (zid != parent_id):
            coll_chip = rism_chip_collection(parent_rec, used_links_page)

        duo = rism_duo(self_chip, coll_chip)
        if duo:
            tags.append(duo)

        tags_html = "".join(tags)

        instr_block = "" if rec["indiv_coll"] == "VirtualColl" else build_instr_block_for_record(rec, include_catalogs=True)

        meta_bits = []
        if rec["indiv_coll"] != "VirtualColl" and rec["composer"]:
            meta_bits.append(f'<div class="meta-block"><span class="label">Composer</span><span class="value">{rec["composer"]}</span></div>')

        lib_val = rec["library"]
        shelf_val = rec["shelfmark"]
        if rec["see_rism"]:
            if lib_val: lib_val += " "
            lib_val += '<span class="see-rism-tag">See RISM</span>'
            if shelf_val: shelf_val += " "
            shelf_val += '<span class="see-rism-tag">See RISM</span>'

        if lib_val:
            meta_bits.append(f'<div class="meta-block"><span class="label">Library</span><span class="value">{lib_val}</span></div>')
        if shelf_val:
            meta_bits.append(f'<div class="meta-block"><span class="label">Shelfmark</span><span class="value">{shelf_val}</span></div>')

        meta_html = "".join(meta_bits)

        # NEW: RISM drawer (variant B2: no earliest/latest visible)
        rism_drawer = ""
        rism_date = clean_str(rec.get("rism_date_raw",""))
        rism_holdings = clean_str(rec.get("rism_holdings_raw",""))
        rism_holdings_count = len(holdings_lines(rism_holdings))

        if rism_date or rism_holdings:
            open_attr = " open" if rism_holdings else ""
            pills = []
            if rism_date:
                pills.append(f'<span class="pill">Date: {escape_textnode(rism_date)}</span>')
            if rism_holdings_count:
                pills.append(f'<span class="pill" style="opacity:.9;">Holdings: {rism_holdings_count}</span>')
            pills_html = "".join(pills)

            holdings_html = holdings_list_html(rism_holdings)
            if holdings_html:
                holdings_html = f"""
          <div>
            <div class="rism-hint" style="margin-bottom:6px;">RISM Holdings (one line per institution):</div>
            {holdings_html}
          </div>"""

            rism_drawer = f"""
    <details class="rism"{open_attr}>
      <summary>
        <div class="rism-left">
          <span class="rism-title">RISM data</span>
          <div class="rism-mini">{pills_html}</div>
        </div>
        <span class="tag tag-rism" style="opacity:.85;">open/close</span>
      </summary>
      <div class="rism-body">
        <div class="rism-hint">RISM has priority over manual data when overlapping.</div>
        <div class="rism-kv">
          <div class="k">RISM Date (text)</div><div class="v">{escape_textnode(rism_date) if rism_date else ''}</div>
        </div>
        {holdings_html}
      </div>
    </details>
"""

        biblio_html = f'<div class="piece-notes"><div class="label">Bibliography:</div><div class="value">{rec["bibliography"]}</div></div>' if (rec["indiv_coll"]!="VirtualColl" and rec["bibliography"]) else ""
        note_html = f'<div class="piece-notes"><div class="label">Note:</div><div class="value">{rec["note"]}</div></div>' if (rec["indiv_coll"]!="VirtualColl" and rec["note"]) else ""
        org_html = f'<div class="piece-notes"><div class="label">Organology:</div><div class="value">{rec["organology"]}</div></div>' if (rec["indiv_coll"]!="VirtualColl" and rec["organology"]) else ""

        conc_html = ""
        if rec["indiv_coll"] != "VirtualColl" and rec["concordances_ids"]:
            cards_html = []
            for cid in rec["concordances_ids"]:
                cr = records.get(cid)
                if not cr:
                    continue
                mt = cr["music_type_raw"]
                st = cr["source_type_raw"]
                mt_tag = f'<span class="tag tag-type">{escape_textnode(mt)}</span>' if mt else ""
                st_tag = f'<span class="tag tag-source">{escape_textnode(st)}</span>' if st else ""
                rchip = rism_chip_self(cr, used_links_page)
                cards_html.append(f"""
      <div class="conc-card">
        <a class="conc-id-link" href="piece-{cid.replace('/','-')}.html" target="_blank" rel="noopener">{escape_textnode(cid)}</a>
        <div class="conc-main">
          <div class="conc-title">{cr["title"] or "(Untitled)"}</div>
          <div class="conc-composer">{cr["composer"] or ""}</div>
          <div class="conc-tags">{mt_tag}{st_tag}{rchip}</div>
        </div>
      </div>""")
            conc_html = f"""
    <div class="conc-block">
      <div class="conc-heading">Linked concordances</div>
      <div class="conc-cards">
        {''.join(cards_html)}
      </div>
    </div>"""

        subpieces_html = ""
        if rec["indiv_coll"] in ("Coll.", "VirtualColl"):
            sub_entries = []
            for pid in ids_in_group:
                if coll_id and pid == coll_id:
                    continue
                pr = records.get(pid)
                if not pr:
                    continue

                sub_instr = "" if pr["indiv_coll"] == "VirtualColl" else build_instr_block_for_record(pr, include_catalogs=True)

                sub_conc = ""
                if pr["concordances_ids"]:
                    n = len(pr["concordances_ids"])
                    sub_conc = f'<div class="sub-entry-conc"><span class="tag tag-conc">{n} concordance{"s" if n!=1 else ""}</span></div>'

                sub_rism = rism_chip_self(pr, used_links_page)

                sub_entries.append(f"""
    <details class="sub-entry">
      <summary>
        <div class="sub-entry-header">
          <div class="sub-entry-title">{escape_textnode(pid)} — {pr["title"] or "(Untitled)"}</div>
          <div class="sub-entry-composer">{pr["composer"] or ""}</div>
        </div>
      </summary>
      <div class="sub-entry-body">
        {sub_instr}
        <div class="subpiece-link" style="margin-top:6px; display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <a href="piece-{pid.replace('/','-')}.html" target="_blank" rel="noopener">Open piece page</a>
          {sub_rism}
        </div>
        {sub_conc}
      </div>
    </details>
            """)

            subpieces_html = f"""
    <div class="detail-subpieces">
      <div class="subpieces-title">Contents</div>
      {''.join(sub_entries)}
    </div>"""

        title_full = f"{zid} — {rec['title_raw'] or '(Untitled)'}"
        page_html = (
            detail_template
            .replace("@@TITLE_FULL@@", html.escape(title_full, quote=False))
            .replace("@@HEADER@@", build_header_html())
            .replace("@@BREADCRUMB@@", breadcrumb_extra)
            .replace("@@PARENT_BTN@@", parent_btn)
            .replace("@@ID@@", escape_textnode(zid))
            .replace("@@TITLE@@", rec["title"] or "<em>(Untitled)</em>")
            .replace("@@COMPOSER@@", rec["composer"] or "")
            .replace("@@TAGS@@", tags_html)
            .replace("@@INSTR@@", instr_block)
            .replace("@@META@@", meta_html)
            .replace("@@RISM_DRAWER@@", rism_drawer)
            .replace("@@BIBLIO@@", biblio_html)
            .replace("@@NOTE@@", note_html)
            .replace("@@ORG@@", org_html)
            .replace("@@CONC@@", conc_html)
            .replace("@@SUBPIECES@@", subpieces_html)
        )
        (OUT_DIR / f"piece-{zid.replace('/','-')}.html").write_text(page_html, encoding="utf-8")

    print("✅ Built docs/")
    print("Index:", (OUT_DIR / "index.html").exists())
    print("CSS:", (OUT_DIR / "style.css").exists())
    print("Pieces:", len(list(OUT_DIR.glob("piece-*.html"))))
    print("SearchTool instruments:", len(all_instr_sorted))

if __name__ == "__main__":
    main()
