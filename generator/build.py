# generator/build.py
# ZinkNET — GitHub Actions builder (Google Sheet -> static site in /docs)
# UNION version (composer dropdown + smart collections + Search Tool + RISM chronology + RISM drawer)
#
# Current index/search features:
# - Sort by: Composer A–Z / Source date earliest first / Source date latest first
# - Specific RISM number filter, in addition to RISM No. being searchable globally
# - Bibliography:
#     * included in global search
#     * dedicated wide multi-select filter
#     * references split by line breaks
#     * Match any / Match all
# - Holdings / Libraries:
#     * dedicated searchable multi-select filter
#     * RISM Holdings sigla used when available
#     * Library-ies (public) sigla used only when no usable RISM Holdings sigla exists
#     * Match any / Match all
# - Smart collection filtering for Search Tool, chronology, composer, bibliography,
#   holdings/libraries, and RISM number.

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

# Column names expected in the Google Sheet
COL_ZINK = "ZINKNET NO."
COL_INDIV = "Indiv. or Coll."
COL_COMP = "Composer"
COL_TITLE = "Title"
COL_CONC = "Concordances"
COL_RISM_LINK = "RISM link"
COL_RISM_NO = "RISM No."
COL_MUSIC_TYPE = "Music type"
COL_SOURCE_TYPE = "Source type"
COL_LIB = "Library-ies (public)"
COL_SHELF = "Shelfmark (public)"
COL_NOTE = "Note"
COL_BIB = "Bibliography"
COL_ORG = "Organology"
COL_CATEGORY = "Category"
COL_INSTR_MAIN = "Instrumentation principal\nRISM extended"
COL_INSTR_ALT = "Instrumentation alternative\nRISM extended"
COL_INSTR_CAT = "Instrumentation from Catalogs"
COL_SEARCH_TOOL = "Search Tool"

# RISM extra fields (optional but used when present)
COL_RISM_HOLDINGS = "RISM Holdings"
COL_RISM_DATE = "RISM Date"
COL_RISM_EARLIEST = "RISM Earliest Year"
COL_RISM_LATEST = "RISM Latest Year"

EM_TITLES = [
    "The Early Trombone : a Catalog of Music",
    "Instrumental Music Specifying Cornett",
    "A Catalog of Music for the Cornett",
    "The Early Trombone",
    "Instrumental Music",
    "Vocal Music",
]
EM_TITLES_SORTED = sorted(EM_TITLES, key=len, reverse=True)

SIGLUM_RE = re.compile(r'(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9])([A-Z]{1,3}-[A-Za-zÀ-ÖØ-öø-ÿ0-9?]+)')
RISM_HOLDING_PAREN_RE = re.compile(r'\(([^()]*)\)')
RISM_SIGLUM_FULL_RE = re.compile(r'^[A-Z]{1,3}-[A-Za-zÀ-ÖØ-öø-ÿ0-9?]+$')

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

def parse_int_safe(x):
    x = clean_numberish(x)
    if not x:
        return None
    try:
        return int(x)
    except ValueError:
        return None

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
    s = s.replace("[", "").replace("]", "")
    parts = re.split(r"[;,\n]+", s)
    return [p.strip() for p in parts if p.strip()]

def unique_preserve_order(items):
    seen = set()
    out = []
    for item in items:
        key = item
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out

def format_uniform_instr(raw_text, alternative=False):
    """
    Any 'LABEL: { ... }' becomes its own line block (braces removed).
    """
    s = clean_str(raw_text)
    if not s:
        return ""

    def repl(m):
        label = m.group(1).strip()
        content = m.group(2).strip()
        return f"\n{label} {content}\n"

    t2 = re.sub(r'([^:]+:\s*)\{([^}]*)\}', repl, s)
    t2 = re.sub(r'\n\s*,\s*', '\n', t2)
    t2 = re.sub(r'\n+', '\n', t2).strip(' \n,')
    if not t2.strip():
        return ""

    heading = "UNIFORM INSTRUMENTATION (ALTERNATIVE)" if alternative else "UNIFORM INSTRUMENTATION"
    body = html.escape(t2, quote=False).replace("\n", "<br>")
    return f'<strong class="instr-label">{heading}</strong><div class="instr-content">{body}</div>'

def parse_zinknet(no):
    """
    Standard catalogue order:
      1. batch prefix: A, then B, then C, ...
      2. main number
      3. subnumber after slash

    Supports:
      - A-1
      - A-682/0
      - B-1
      - C-12/3
      - 682/0

    Entries without prefix are placed after prefixed batches.
    """
    s = clean_str(no)
    if not s:
        return (10**9, 10**9, 10**9, "")

    pm = re.match(r"^\s*([A-Za-z]+)\s*[-–—]\s*", s)
    prefix = pm.group(1).upper() if pm else ""

    if prefix:
        batch_rank = 0
        for ch in prefix:
            if "A" <= ch <= "Z":
                batch_rank = batch_rank * 26 + (ord(ch) - ord("A") + 1)
            else:
                batch_rank = 10**6
                break
    else:
        batch_rank = 10**6

    m = re.search(r"(\d+)(?:\s*/\s*(\d+))?", s)
    if not m:
        return (batch_rank, 10**9, 10**9, s)

    main = int(m.group(1))
    sub = int(m.group(2)) if m.group(2) is not None else 0

    return (batch_rank, main, sub, s)

def group_id(no):
    s = clean_str(no)
    return s.split("/", 1)[0] if "/" in s else s

def get_col(row, name):
    return row[name] if (name in row and not pd.isna(row[name])) else ""

def norm_music_type(s):
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

def source_categories_for_filter(raw):
    """
    Simple source categories for user-facing filtering:
      Ms.*  -> Manuscript
      Print -> Print
      Txt   -> Text
    """
    s = clean_str(raw)
    if not s:
        return set()

    low = s.lower().strip()

    if low == "txt" or low.startswith("txt"):
        return {"Text"}
    if "print" in low:
        return {"Print"}
    if "ms" in low:
        return {"Manuscript"}

    return {s}

def manuscript_details_for_filter(raw):
    """
    Contextual manuscript details.
    Only manuscript-related details are returned.
    Print and Txt are intentionally omitted.

    Rules:
      Ms.                         -> Ms.
      Ms. Autograph               -> Ms. Autograph
      Ms. Autograph (partial)     -> Ms. Autograph
      Ms. Autograph (poss.)       -> Ms. Autograph
      Ms. Copy                    -> Ms. Copy
      Ms. Autograph ; Ms. Copy    -> Ms. Autograph + Ms. Copy
    """
    s = clean_str(raw)
    if not s:
        return set()

    out = set()
    parts = re.split(r"\s*;\s*", s)

    for p in parts:
        p = p.strip()
        low = p.lower()

        if not low:
            continue
        if low.startswith("print") or low.startswith("txt"):
            continue
        if "autograph" in low:
            out.add("Ms. Autograph")
        elif "copy" in low:
            out.add("Ms. Copy")
        elif low.startswith("ms"):
            out.add("Ms.")

    return out

def bibliography_refs(raw):
    """
    Split bibliography cells into individual references.
    In the sheet, multiple references are separated by line breaks.
    """
    s = clean_str(raw)
    if not s:
        return []
    refs = []
    for part in re.split(r"\r?\n+", s):
        part = re.sub(r"\s+", " ", part).strip()
        if part:
            refs.append(part)
    return unique_preserve_order(refs)

def rism_holdings_sigla(raw):
    """
    Extract sigla from RISM Holdings.
    Holdings lines reliably contain the RISM siglum in parentheses.

    "(No holdings found)" is not usable as holdings data and returns [].
    """
    s = clean_str(raw)
    if not s:
        return []
    if re.search(r"no\s+holdings\s+found", s, flags=re.I):
        return []

    out = []
    for line in re.split(r"\r?\n+", s):
        for m in RISM_HOLDING_PAREN_RE.finditer(line):
            candidate = m.group(1).strip()
            if RISM_SIGLUM_FULL_RE.fullmatch(candidate):
                out.append(candidate)
    return unique_preserve_order(out)

def public_library_sigla(raw):
    """
    Extract sigla from Library-ies (public).
    "[See RISM]" markers are ignored.
    This field is used only when no usable RISM Holdings sigla exist.
    """
    s = clean_str(raw)
    if not s:
        return []

    s = re.sub(r"\[\s*see\s+rism\s*\]", " ", s, flags=re.I)
    matches = SIGLUM_RE.findall(s)
    return unique_preserve_order(matches)

def holdings_libraries_sigla(holdings_raw, library_raw):
    """
    Filter logic requested by the project:
      - if RISM Holdings yields actual sigla, use those and ignore Library-ies (public);
      - otherwise, fall back to Library-ies (public).
    """
    from_rism = rism_holdings_sigla(holdings_raw)
    if from_rism:
        return from_rism
    return public_library_sigla(library_raw)

def norm_url(u):
    return clean_str(u).strip()

def composer_tokens(raw):
    s = clean_str(raw).lower()
    s = re.sub(r"[^a-zà-öø-ÿ\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def sort_text_key(raw):
    return clean_str(raw).casefold()

# =========================
# Search Tool parser (scenario-based)
# =========================
def _split_top_level(s, sep):
    out, buf, depth = [], [], 0
    for ch in s:
        if ch == "[":
            depth += 1
        elif ch == "]":
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
    s = clean_str(text)
    if not s:
        return []
    s = re.sub(r"\s+", " ", s).strip()
    top = _split_top_level(s, ",")

    common_items = {}
    branch_blocks = None

    for seg in top:
        seg = seg.strip()
        if not seg:
            continue

        if seg.startswith("[") and seg.endswith("]") and "/" in seg:
            parts = _split_top_level(seg, "/")
            if len(parts) >= 2 and all(p.strip().startswith("[") and p.strip().endswith("]") for p in parts):
                branch_blocks = [p.strip() for p in parts]
                continue

        it = _parse_item_token(seg)
        if it:
            name, qty = it
            common_items[name] = common_items.get(name, 0) + qty

    scenarios = []
    if branch_blocks:
        for bb in branch_blocks:
            base, choices = _parse_branch(bb)
            base2 = dict(common_items)
            for k, v in base.items():
                base2[k] = base2.get(k, 0) + v
            scenarios.extend(_expand_choices(base2, choices, limit=limit))
    else:
        base = dict(common_items)
        choices = []
        for seg in top:
            seg = seg.strip()
            if not seg:
                continue
            if seg.startswith("[") and seg.endswith("]"):
                ch = _parse_choice_block(seg)
                if ch:
                    choices.append(ch)
        scenarios = _expand_choices(base, choices, limit=limit)

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
    if self_chip_html and coll_chip_html:
        return f'<span class="rism-duo">{self_chip_html}<span class="rism-divider"></span>{coll_chip_html}</span>'
    return self_chip_html or coll_chip_html or ""

# =========================
# HEADER
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
      <div class="partner-text">In collaboration with</div>

      <div class="logo-column">
        <div class="hem-slot">
          {hem_block}
        </div>
        <div class="rism-slot">
          {rism_block}
        </div>
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
  padding: 9px 22px 8px;
  border-bottom: 1px solid var(--border-subtle);
  background: linear-gradient(to right,rgba(255,255,255,0.98),rgba(245,247,255,0.96));
  position: sticky;
  top:0;
  z-index:20;
  backdrop-filter: blur(10px);
}

.header-grid{
  display:grid;
  grid-template-columns: minmax(0,1fr) auto;
  gap: 18px;
  align-items:center;
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
  align-items:flex-end;
  justify-content:flex-end;
  gap: 10px;
  min-width: max-content;
  padding-top:0;
}

.logo-column{
  display:flex;
  flex-direction:column;
  align-items:center;
  gap: 7px;
}

.hem-slot,
.rism-slot{
  display:flex;
  justify-content:center;
  align-items:center;
}

.partner-text{
  color:var(--muted);
  font-size:0.78rem;
  line-height:1.0;
  white-space:nowrap;
  padding-bottom: 10px;
}

.hem-logo,
.rism-logo{
  display:block;
  width:auto;
  filter: drop-shadow(0 8px 18px rgba(15,23,42,0.10));
}

.hem-logo{
  height: 68px;
}

.rism-logo{
  height: 30px;
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
  .header-grid{
    grid-template-columns: 1fr;
    align-items:start;
  }

  .right{
    justify-content:start;
  }

  .meta-line{
    white-space:normal;
  }
}

/* Layout */
.shell { max-width:1400px; margin:0 auto; padding:16px 20px 26px; }
.layout { display:grid; grid-template-columns: minmax(260px,320px) minmax(0,1fr); gap:16px; }

@media (max-width: 960px) {
  .layout { grid-template-columns: 1fr; }
}

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

.catalogue-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
}

.catalogue-head h2{
  margin:0;
}

.catalogue-sort{
  display:flex;
  align-items:center;
  gap:7px;
  flex-wrap:wrap;
  justify-content:flex-end;
}

.catalogue-sort label{
  margin:0;
  font-size:0.72rem;
  text-transform:uppercase;
  letter-spacing:.13em;
  color:var(--muted);
}

.catalogue-sort select{
  padding:6px 10px;
  border-radius:999px;
  border:1px solid var(--border-subtle);
  background:#fafaff;
  color:var(--text);
  font-family:inherit;
  font-size:0.82rem;
  outline:none;
  cursor:pointer;
}

.filters label {
  display:block;
  font-size:0.78rem;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:var(--muted);
  margin-bottom:6px;
}

.filters input[type="text"],
.filters input[type="number"] {
  width:100%;
  border-radius:999px;
  border:1px solid var(--border-subtle);
  background:#fafaff;
  padding:7px 11px;
  color:var(--text);
  font-size:0.9rem;
  outline:none;
}

.filters select {
  padding:7px 10px;
  border-radius:999px;
  border:1px solid var(--border-subtle);
  background:#fafaff;
  font-size:0.85rem;
  color:var(--text);
  outline:none;
  cursor:pointer;
}

.filters button {
  font-family: inherit;
}


/* Search panel — compact collapsible sections */
.search-card-header{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:12px;
  margin-bottom:10px;
}

.search-card-header h2{
  margin:0;
}

.clear-top-btn{
  flex:0 0 auto;
  padding:5px 10px !important;
  font-size:.74rem !important;
  font-weight:650;
  background:#fff !important;
  border-color:#c5c8e6 !important;
  color:#4b5563 !important;
  white-space:nowrap;
  margin-top:-1px;
}

.clear-top-btn:hover{
  border-color:#9db5ff !important;
  background:#fafaff !important;
  color:var(--accent) !important;
}

.filter-field label{
  display:block;
  font-size:0.74rem;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:var(--muted);
  margin-bottom:6px;
  font-weight:650;
}

.field-hint{
  margin-top:4px;
  font-size:.76rem;
  color:#6b7280;
}

.primary-search-block{
  border:1px solid rgba(208,213,235,0.95);
  background:linear-gradient(180deg,#ffffff,#fbfcff);
  border-radius:16px;
  padding:11px;
  box-shadow:0 8px 22px rgba(15,23,42,0.045);
}

details.filter-section{
  position:relative;
  z-index:1;
  border:1px solid rgba(208,213,235,0.95);
  background:linear-gradient(180deg,#fbfcff,#f6f7ff);
  border-radius:16px;
  overflow:visible;
}

details.filter-section[open]{
  z-index:100;
  background:#ffffff;
  border-color:var(--border-strong);
  box-shadow:0 8px 22px rgba(15,23,42,0.07);
}

details.filter-section > summary{
  list-style:none;
  cursor:pointer;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:9px 11px;
  user-select:none;
}

details.filter-section > summary::-webkit-details-marker{
  display:none;
}

.section-title{
  display:flex;
  flex-direction:column;
  gap:1px;
  min-width:0;
}

.section-title strong{
  font-size:.76rem;
  text-transform:uppercase;
  letter-spacing:.13em;
  color:#374151;
  line-height:1.1;
}

.section-title span{
  font-size:.76rem;
  color:#6b7280;
  line-height:1.2;
}

.section-arrow{
  color:#6b7280;
  transition:transform .16s ease;
  font-size:1rem;
}

details.filter-section[open] .section-arrow{
  transform:rotate(90deg);
  color:var(--accent);
}

.section-body{
  padding:11px;
  border-top:1px solid rgba(208,213,235,0.72);
  display:flex;
  flex-direction:column;
  gap:10px;
}

.section-body{
  position:relative;
  overflow:visible;
}

/* Instrumentation simple-search dropdown */
.instr-suggest-wrap{
  position:relative;
}

.instr-menu{
  display:none;
  position:relative;
}

.instr-menu .instr-list{
  position:absolute;
  top:4px;
  left:0;
  right:0;
  background:#fff;
  border:1px solid var(--border-subtle);
  border-radius:14px;
  box-shadow:0 14px 30px rgba(15,23,42,0.10);
  max-height:5000px;
  overflow:auto;
  z-index:80;
  padding:6px;
}

.instr-item{
  padding:7px 10px;
  border-radius:12px;
  cursor:pointer;
  font-size:0.9rem;
  color:var(--text);
  display:flex;
  justify-content:space-between;
  gap:10px;
}

.instr-item:hover{
  background: rgba(35,75,184,0.06);
}

.instr-item-count{
  color:#6b7280;
  font-size:.8rem;
  white-space:nowrap;
}

.filters-row { display:flex; flex-direction:column; gap:10px; }
.filter-inline { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.filter-grid-2 { display:grid; grid-template-columns: 1fr 1fr; gap:8px; }

.filter-mode-row{
  margin-bottom:6px;
}

.filter-mode-row select{
  font-size:0.8rem;
  padding:6px 9px;
}

.filter-dropdown-wrap{
  position:relative;
}

.wide-dropdown-toggle{
  width:100%;
  text-align:left;
  border-radius:14px;
  border:1px solid var(--border-subtle);
  background:#fafaff;
  color:var(--text);
  padding:8px 11px;
  font-size:0.88rem;
  cursor:pointer;
}

.wide-dropdown-toggle:hover{
  border-color:var(--border-strong);
}

.wide-dropdown-menu{
  display:none;
  position:absolute;
  z-index:5000;
  top:calc(100% + 5px);
  left:0;
  width:min(760px, calc(100vw - 54px));
  max-height:360px;
  overflow:auto;
  padding:7px;
  background:#ffffff;
  border:1px solid var(--border-subtle);
  border-radius:16px;
  box-shadow:0 18px 42px rgba(15,23,42,0.18);
}

.wide-dropdown-item{
  width:100%;
  display:block;
  border:none;
  background:transparent;
  text-align:left;
  padding:9px 10px;
  border-radius:12px;
  cursor:pointer;
  color:var(--text);
  font-size:0.86rem;
  line-height:1.35;
  white-space:normal;
}

.wide-dropdown-item:hover{
  background:rgba(35,75,184,0.06);
}

.wide-dropdown-item.is-selected{
  background:rgba(139,92,246,0.10);
  color:var(--violet-text);
  font-weight:650;
}

.active-filter-chips{
  margin-top:7px;
  display:flex;
  flex-wrap:wrap;
  gap:6px;
}

.active-filter-chip{
  display:inline-flex;
  align-items:center;
  gap:5px;
  max-width:100%;
  border:1px solid var(--tag-neutral-border);
  background:#ffffff;
  color:var(--muted);
  border-radius:999px;
  padding:3px 8px;
  font-size:0.72rem;
  cursor:pointer;
}

.active-filter-chip .chip-text{
  display:inline-block;
  max-width:235px;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

.active-filter-chip:hover{
  border-color:var(--violet-border);
  color:var(--violet-text);
}

.library-menu{
  display:none;
  position:relative;
}

.library-menu .library-list{
  position:absolute;
  top:4px;
  left:0;
  right:0;
  background:#fff;
  border:1px solid var(--border-subtle);
  border-radius:14px;
  box-shadow:0 14px 30px rgba(15,23,42,0.10);
  max-height:260px;
  overflow:auto;
  z-index:5000;
  padding:6px;
}

.library-item{
  padding:7px 10px;
  border-radius:12px;
  cursor:pointer;
  font-size:0.9rem;
  color:var(--text);
}

.library-item:hover{
  background: rgba(35,75,184,0.06);
}

.entries {
  max-height: calc(100vh - 170px);
  overflow:auto;
  padding-right:4px;
}

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

summary {
  list-style:none;
  cursor:pointer;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
}

summary::-webkit-details-marker { display:none; }

.entry-main { display:flex; flex-direction:column; gap:3px; }

.entry-id {
  font-weight:650;
  font-size:0.96rem;
  color:#020617;
}

.entry-composer {
  font-size:0.85rem;
  color:var(--muted);
  display:flex;
  flex-wrap:wrap;
  gap:6px;
  align-items:center;
}

.entry-tags {
  display:flex;
  flex-wrap:wrap;
  gap:4px;
  margin-top:3px;
  align-items:center;
}

.tag {
  font-size:0.7rem;
  padding:3px 7px;
  border-radius:999px;
  border:1px solid var(--tag-neutral-border);
  color:var(--muted);
  background:var(--tag-neutral-bg);
}

.tag-type {
  text-transform:uppercase;
  letter-spacing:.12em;
  border-color:#9db5ff;
  background:#e1e7ff;
  color:#1d3578;
  font-weight:650;
}

.tag-source {
  text-transform:uppercase;
  letter-spacing:.12em;
}

.tag-count {
  background: var(--green-collection-bg);
  border-color: var(--green-collection);
  color: var(--green-collection);
  font-weight:650;
}

.tag-conc {
  border:1px solid var(--border-subtle);
  background:#ffffff;
}

.tag-rism{
  border-color: var(--violet-border);
  background: var(--violet-bg);
  color: var(--violet-text);
  text-transform:uppercase;
  letter-spacing:.12em;
  font-weight:650;
}

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

.see-rism-tag {
  display:inline-flex;
  align-items:center;
  margin-left:6px;
  padding:2px 6px;
  border-radius:999px;
  border:1px solid var(--violet-border);
  background: var(--violet-bg);
  font-size:0.7rem;
  text-transform:uppercase;
  letter-spacing:.12em;
  color: var(--violet-text);
}

.entry-arrow {
  font-size:1.1rem;
  color:var(--muted);
  transition: transform .15s ease, color .15s ease;
}

details[open] > summary .entry-arrow {
  transform: rotate(90deg);
  color:var(--accent);
}

.entry-body {
  border-top:1px solid #dde1f7;
  margin-top:8px;
  padding-top:8px;
  font-size:0.9rem;
}

dl.meta {
  margin:0;
  display:grid;
  grid-template-columns: minmax(0,150px) minmax(0,1fr);
  row-gap:4px;
  column-gap:12px;
}

dt.meta-label {
  font-weight:600;
  color:var(--muted);
  font-size:0.8rem;
}

dd.meta-value {
  margin:0;
}

.instr-block { margin-top:8px; margin-bottom:8px; }

.instr-strip-uniform {
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  justify-content:center;
}

.instr-pill {
  flex:0 1 470px;
  background:var(--accent-soft);
  border-radius:14px;
  padding:8px 11px;
  border:1px solid var(--pill-border);
  font-size:0.85rem;
}

.instr-pill.catalog-full {
  margin-top:8px;
  width:100%;
  background:#fdfdff;
  border-radius:14px;
  padding:8px 11px;
  border:1px solid var(--pill-border);
  font-size:0.85rem;
}

.instr-label {
  font-size:0.72rem;
  text-transform:uppercase;
  letter-spacing:0.12em;
  display:block;
  margin-bottom:3px;
  color:#25345f;
}

.instr-content {
  margin-top:2px;
  line-height:1.35;
}

.subpieces {
  margin-top:8px;
  border-radius:14px;
  border:1px dashed var(--border-subtle);
  padding:7px 9px 7px;
  background:#f2f3ff;
}

.subpieces-title {
  font-size:0.78rem;
  text-transform:uppercase;
  letter-spacing:.13em;
  color:var(--muted);
  margin-bottom:4px;
  display:flex;
  gap:8px;
  align-items:center;
}

.subpieces-matchcount{
  font-size:.74rem;
  color: var(--violet-text);
  opacity:.85;
}

.subpiece-line {
  padding:6px 0;
  border-top:1px solid #d8ddf5;
  font-size:0.88rem;
  display:flex;
  flex-direction:column;
  gap:2px;
}

.subpiece-line:first-of-type { border-top:none; }

.subpiece-line.is-match {
  border-top:1px solid rgba(139,92,246,0.35);
  background: rgba(139,92,246,0.07);
  border-radius:10px;
  padding-left:8px;
  padding-right:8px;
}

.subpiece-id {
  font-weight:600;
  color:#020617;
}

.subpiece-meta {
  font-size:0.8rem;
  color:var(--muted);
}

.subpiece-link {
  font-size:0.78rem;
  display:flex;
  gap:8px;
  align-items:center;
  flex-wrap:wrap;
}

.subpiece-conc-tag { margin-top:2px; }
.entry-open-link { margin-top:6px; font-size:0.8rem; }

.no-results {
  margin-top:10px;
  padding:10px 12px;
  border-radius:10px;
  border:1px solid var(--border-subtle);
  font-size:0.9rem;
  color:var(--muted);
}


/* Source-aware open index cards */
.index-card-grid{
  display:grid;
  grid-template-columns:minmax(0,1fr) minmax(190px,235px);
  gap:10px;
  align-items:start;
}

@media (max-width: 720px){
  .index-card-grid{ grid-template-columns:1fr; }
}

.index-work-panel,
.index-contents-panel,
.index-source-panel{
  border:1px solid #d4d9ef;
  background:#ffffff;
  border-radius:15px;
  padding:9px 11px;
  min-width:0;
}

.index-work-panel,
.index-contents-panel{
  background:linear-gradient(180deg,#ffffff,#f8f9ff);
}

.index-panel-title{
  font-size:.70rem;
  text-transform:uppercase;
  letter-spacing:.13em;
  color:var(--muted);
  font-weight:750;
  margin-bottom:6px;
}

.index-work-title{
  font-size:.92rem;
  font-weight:720;
  color:#111827;
  line-height:1.25;
  overflow-wrap:anywhere;
}

.index-work-meta{
  margin-top:3px;
  color:var(--muted);
  font-size:.80rem;
  line-height:1.30;
}

.index-instr-integrated{
  margin-top:8px;
  border-top:1px solid #e1e5f5;
  padding-top:7px;
}

.index-instr-label{
  display:block;
  font-size:.68rem;
  text-transform:uppercase;
  letter-spacing:.12em;
  color:#25345f;
  font-weight:750;
  margin-bottom:3px;
}

.index-instr-text{
  color:#1f2937;
  font-size:.86rem;
  line-height:1.33;
  overflow-wrap:anywhere;
}

.index-instr-alt-label{
  display:inline-block;
  margin-right:4px;
  font-size:.68rem;
  text-transform:uppercase;
  letter-spacing:.10em;
  color:#53618a;
  font-weight:750;
}

.index-source-grid{
  display:grid;
  grid-template-columns:minmax(0,76px) minmax(0,1fr);
  gap:4px 9px;
}

.index-source-k{
  color:var(--muted);
  font-size:.76rem;
  font-weight:650;
}

.index-source-v{
  color:#1f2937;
  font-size:.84rem;
  overflow-wrap:anywhere;
}

.muted-value{ color:#9ca3af; }

.index-soft-ref{
  font-size:.70rem;
  color:#8a91a0;
  font-weight:600;
  letter-spacing:.035em;
  line-height:1.1;
}

.index-content-row.subpiece-line{
  display:grid;
  grid-template-columns:minmax(48px,58px) minmax(0,1fr);
  gap:8px;
  border-top:1px solid #e1e5f5;
  padding:7px 0;
  font-size:.88rem;
  background:transparent;
}

.index-content-row.subpiece-line:first-of-type{
  border-top:none;
  padding-top:0;
}

.index-content-row.subpiece-line.is-match{
  border-top:1px solid rgba(139,92,246,0.35);
  background:rgba(139,92,246,0.07);
  border-radius:10px;
  padding-left:8px;
  padding-right:8px;
}

.index-piece-ref{
  font-size:.66rem;
  color:#8a91a0;
  font-weight:600;
  letter-spacing:.035em;
  line-height:1.1;
  padding-top:2px;
}

.index-content-title{
  font-size:.86rem;
  font-weight:650;
  color:#111827;
  line-height:1.25;
  overflow-wrap:anywhere;
}

.index-content-meta{
  font-size:.78rem;
  color:var(--muted);
  margin-top:1px;
  line-height:1.28;
}

.index-content-instr{
  font-size:.78rem;
  color:#1f2937;
  margin-top:3px;
  line-height:1.28;
  overflow-wrap:anywhere;
}

.index-content-extra{
  margin-top:4px;
  display:flex;
  flex-wrap:wrap;
  gap:4px;
}

/* Detail pages */
.detail-shell {
  max-width:900px;
  margin:0 auto;
  padding:18px 16px 28px;
}

.detail-card {
  background:var(--bg-soft);
  border-radius:22px;
  border:1px solid var(--border-subtle);
  box-shadow:0 18px 45px rgba(15,23,42,0.12);
  padding:20px;
}

.detail-header {
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:10px;
  margin-bottom:10px;
}

.detail-title {
  font-size:1.1rem;
  font-weight:650;
  margin:0;
  color:#020617;
}

.detail-composer {
  margin:2px 0 0;
  font-size:0.9rem;
  color:var(--muted);
}

.breadcrumbs {
  font-size:0.8rem;
  color:var(--muted);
  margin-bottom:10px;
}

.detail-tags {
  display:flex;
  flex-wrap:wrap;
  gap:4px;
  justify-content:flex-end;
  align-items:center;
}

.piece-meta {
  display:flex;
  flex-wrap:wrap;
  gap:12px 24px;
  font-size:0.9rem;
  margin:6px 0;
}

.meta-block span.label {
  font-weight:600;
  font-size:0.8rem;
  color:var(--muted);
  display:block;
}

.meta-block span.value {
  display:block;
}

.piece-notes {
  font-size:0.88rem;
  margin-top:8px;
}

.piece-notes .label {
  font-weight:600;
  color:var(--muted);
  display:block;
  margin-bottom:3px;
}

.conc-block { margin-top:14px; }

.conc-heading {
  font-size:0.78rem;
  text-transform:uppercase;
  letter-spacing:.13em;
  color:var(--muted);
  margin-bottom:6px;
}

.conc-cards {
  display:flex;
  flex-direction:column;
  gap:6px;
}

.conc-card {
  border-radius:14px;
  border:1px solid var(--border-subtle);
  background:#ffffff;
  padding:7px 9px;
  display:flex;
  gap:8px;
  align-items:flex-start;
  font-size:0.85rem;
}

.conc-id-link {
  font-weight:600;
  padding:3px 8px;
  border-radius:999px;
  border:1px solid var(--accent);
  background:var(--accent-soft);
  white-space:nowrap;
}

.conc-main { flex:1; min-width:0; }

.conc-title {
  font-weight:500;
  color:#020617;
}

.conc-composer {
  font-size:0.78rem;
  color:var(--muted);
}

.conc-tags {
  margin-top:2px;
  display:flex;
  flex-wrap:wrap;
  gap:4px;
  align-items:center;
}

.detail-subpieces { margin-top:16px; }

.sub-entry {
  border-radius:16px;
  border:1px solid var(--border-subtle);
  background:#f6f7ff;
  padding:8px 9px;
  margin-bottom:6px;
}

.sub-entry summary {
  padding:0;
  cursor:pointer;
}

.sub-entry-header {
  display:flex;
  flex-direction:column;
  gap:2px;
}

.sub-entry-title {
  font-size:0.9rem;
  font-weight:600;
  color:#020617;
}

.sub-entry-composer {
  font-size:0.8rem;
  color:var(--muted);
}

.sub-entry-body {
  border-top:1px solid #dde1f0;
  margin-top:6px;
  padding-top:6px;
  font-size:0.85rem;
}

.sub-entry-body .instr-pill,
.sub-entry-body .instr-pill.catalog-full {
  background:#ffffff;
  border-style:dashed;
}

.sub-entry-conc { margin-top:4px; }

.composer-menu{
  display:none;
  position:relative;
}

.composer-menu .composer-list{
  position:absolute;
  top:4px;
  left:0;
  right:0;
  background:#fff;
  border:1px solid var(--border-subtle);
  border-radius:14px;
  box-shadow:0 14px 30px rgba(15,23,42,0.10);
  max-height:240px;
  overflow:auto;
  z-index:5000;
  padding:6px;
}

.composer-item{
  padding:7px 10px;
  border-radius:12px;
  cursor:pointer;
  font-size:0.9rem;
  color:var(--text);
}

.composer-item:hover{
  background: rgba(35,75,184,0.06);
}

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

.rism-left{
  display:flex;
  align-items:center;
  gap:8px;
  flex-wrap:wrap;
}

.rism-title{
  font-size:.78rem;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:var(--violet-text);
  font-weight:800;
}

.rism-mini{
  display:flex;
  gap:6px;
  flex-wrap:wrap;
  align-items:center;
}

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
}

.rism-kv{
  display:grid;
  grid-template-columns: minmax(0,120px) minmax(0,1fr);
  gap:6px 10px;
  font-size:.88rem;
}

.rism-kv .k{
  color:var(--muted);
  font-weight:600;
  font-size:.80rem;
}

.rism-kv .v{
  color:#111827;
}

.rism-holdings{
  margin:0;
  padding-left:16px;
  font-size:.88rem;
  line-height:1.35;
  max-height: 260px;
  overflow:auto;
}
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
    return [ln.strip() for ln in re.split(r"\r?\n", txt) if ln.strip()]

def holdings_list_html(txt):
    lines = holdings_lines(txt)
    if not lines:
        return ""
    lis = "".join(f"<li>{html.escape(ln, quote=False)}</li>" for ln in lines)
    return f'<ul class="rism-holdings">{lis}</ul>'

def json_attr(obj):
    return escape_attr(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))

def piece_value_payload(records, piece_ids, value_getter, header_rec=None):
    """
    Produce JSON payload for piece-level filters.
    For collections, a matching collection/header notice is added as "__HEADER__".
    """
    payload = []
    if header_rec is not None:
        header_values = value_getter(header_rec)
        if header_values:
            payload.append({"pid": "__HEADER__", "values": header_values})

    for pid in piece_ids:
        rr = records.get(pid)
        if not rr:
            continue
        values = value_getter(rr)
        payload.append({"pid": pid, "values": values})
    return payload

def abbreviate_title(raw, max_len=90):
    """
    Short display title for index-open WORK / CONTENTS blocks.
    The full diplomatic title stays available in the page detail and in the HTML title attribute.
    """
    s = clean_str(raw)
    if not s:
        return ""
    if len(s) <= max_len:
        return s

    separators = [" | ", ". ", "; ", ": ", " – ", " — ", " - "]
    candidates = []
    for sep in separators:
        idx = s.find(sep)
        if 35 <= idx <= max_len:
            candidates.append(idx)

    if candidates:
        cut = min(candidates)
        return s[:cut].rstrip(" .;:|–—-") + "…"

    cut = s.rfind(" ", 0, max_len)
    if cut < 45:
        cut = max_len
    return s[:cut].rstrip(" .;:|–—-,") + "…"

def abbreviated_title_html(raw, max_len=90):
    raw_s = clean_str(raw)
    short = abbreviate_title(raw_s, max_len=max_len)
    if not short:
        return ""
    title_attr = f' title="{escape_attr(raw_s)}"' if raw_s and short != raw_s else ""
    return f'<span{title_attr}>{escape_textnode(short)}</span>'

def is_manuscript_source_type(raw):
    return "Manuscript" in source_categories_for_filter(raw)

def is_print_source_type(raw):
    return "Print" in source_categories_for_filter(raw)

def source_family_for_records(records_list):
    """
    Source family for the index-open right column.
    Manuscript wins over Print because manuscript identity is more source-specific.
    """
    has_ms = any(is_manuscript_source_type(r.get("source_type_raw", "")) for r in records_list)
    if has_ms:
        return "manuscript"
    has_print = any(is_print_source_type(r.get("source_type_raw", "")) for r in records_list)
    if has_print:
        return "print"
    return "other"

def manuscript_identity_raw(rec):
    lib = clean_str(rec.get("library_raw", ""))
    shelf = clean_str(rec.get("shelfmark_raw", ""))
    return " ".join([x for x in [lib, shelf] if x]).strip()

def first_manuscript_identity_raw(records_list):
    for rec in records_list:
        if is_manuscript_source_type(rec.get("source_type_raw", "")):
            ident = manuscript_identity_raw(rec)
            if ident:
                return ident
    for rec in records_list:
        ident = manuscript_identity_raw(rec)
        if ident:
            return ident
    return ""

def index_primary_label_raw(rec, group_recs=None):
    """
    Main bold identity in the index.
    - Composer when present.
    - For manuscripts without composer: Library + Shelfmark.
    - Otherwise blank, so the title line remains the main identifier.
    """
    comp = clean_str(rec.get("composer_raw", ""))
    if comp:
        return comp

    group_recs = group_recs or [rec]
    if source_family_for_records(group_recs) == "manuscript":
        ident = first_manuscript_identity_raw(group_recs)
        if ident:
            return ident

    return ""

def index_instrumentation_html(rec):
    """
    Compact instrumentation block for the open index card.
    It keeps the information close to WORK / CONTENTS instead of showing it as a detached old-style pill.
    """
    bits = []
    if clean_str(rec.get("instr_rism_main_raw", "")):
        bits.append(escape_textnode(rec.get("instr_rism_main_raw", "")))
    if clean_str(rec.get("instr_rism_alt_raw", "")):
        bits.append(
            '<span class="index-instr-alt-label">Alternative</span> '
            + escape_textnode(rec.get("instr_rism_alt_raw", ""))
        )
    if not bits and clean_str(rec.get("instr_catalogs_raw", "")):
        bits.append(escape_with_italics(rec.get("instr_catalogs_raw", "")))
    return "<br>".join(bits)

def build_index_source_panel(rec, group_recs=None):
    """
    Right column for open index cards.
    PRINT: Publisher / Place / Year placeholders.
    MANUSCRIPTS: Library / Shelfmark / Year.
    No RISM Online link here; RISM remains in the tag row and detail page.
    """
    group_recs = group_recs or [rec]
    family = source_family_for_records(group_recs)

    if family == "print":
        year = escape_textnode(rec.get("rism_date_raw", "")) or "—"
        return f"""
          <aside class="index-source-panel">
            <div class="index-panel-title">PRINT</div>
            <div class="index-source-grid">
              <div class="index-source-k">Publisher</div><div class="index-source-v muted-value">—</div>
              <div class="index-source-k">Place</div><div class="index-source-v muted-value">—</div>
              <div class="index-source-k">Year</div><div class="index-source-v">{year}</div>
            </div>
          </aside>"""

    if family == "manuscript":
        ident_rec = None
        for rr in group_recs:
            if is_manuscript_source_type(rr.get("source_type_raw", "")) and manuscript_identity_raw(rr):
                ident_rec = rr
                break
        ident_rec = ident_rec or rec

        lib = escape_textnode(ident_rec.get("library_raw", ""))
        shelf = escape_textnode(ident_rec.get("shelfmark_raw", ""))
        year = escape_textnode(rec.get("rism_date_raw", "")) or "—"

        return f"""
          <aside class="index-source-panel">
            <div class="index-panel-title">MANUSCRIPTS</div>
            <div class="index-source-grid">
              <div class="index-source-k">Library</div><div class="index-source-v">{lib or "—"}</div>
              <div class="index-source-k">Shelfmark</div><div class="index-source-v"><span class="index-soft-ref">{shelf or "—"}</span></div>
              <div class="index-source-k">Year</div><div class="index-source-v">{year}</div>
            </div>
          </aside>"""

    return f"""
          <aside class="index-source-panel">
            <div class="index-panel-title">SOURCE</div>
            <div class="index-source-grid">
              <div class="index-source-k">Type</div><div class="index-source-v">{escape_textnode(rec.get("source_type_raw", "")) or "—"}</div>
            </div>
          </aside>"""

# =========================
# HTML templates
# =========================
index_template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ZinkNET — Interactive catalogue</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="style.css?v=source-aware-2026-05-29">
</head>
<body>
@@HEADER@@
<main class="shell">
  <div class="layout">
    <section class="card search-card">
      <div class="card-header search-card-header">
        <h2>Search & filters</h2>
        <button id="clearAllFilters" type="button" class="tag clear-top-btn">
          Clear all filters
        </button>
      </div>

      <div class="filters">
        <div class="filters-row">

          <div class="primary-search-block">
            <div class="filter-field">
              <label for="searchInput">Search all</label>
              <input id="searchInput" type="text" placeholder="Composer, title, number, library, bibliography…" />
              <div class="field-hint">Broad search across the whole catalogue.</div>
            </div>
          </div>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Main filters</strong>
                <span>Composer, music type, source category</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field" style="position:relative;">
                <label for="composerInput">Composer</label>
                <input id="composerInput" type="text" placeholder="Type: von, moritz, hessen…" autocomplete="off" />
                <div class="composer-menu" id="composerMenu">
                  <div class="composer-list" id="composerList"></div>
                </div>
              </div>

              <div class="filter-field">
                <label>Music type</label>
                <div class="filter-inline">
                  <select id="musicFilter"><option value="">All music types</option></select>
                </div>
              </div>

              <div class="filter-field">
                <label>Source category</label>
                <div class="filter-inline">
                  <select id="sourceFilter"><option value="">All source categories</option></select>
                </div>
              </div>

              <div class="filter-field" id="msDetailBlock" style="display:none;">
                <label>Manuscript detail</label>
                <div class="filter-inline">
                  <select id="msDetailFilter"><option value="">All manuscript details</option></select>
                </div>
              </div>
            </div>
          </details>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Instrumentation</strong>
                <span>Simple search and advanced count rules</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field instr-suggest-wrap">
                <label for="instrInput">Simple search</label>
                <input id="instrInput" type="text" placeholder="Type: cnto, trb, fag, bc…" autocomplete="off" />
                <div class="instr-menu" id="instrMenu">
                  <div class="instr-list" id="instrList"></div>
                </div>
                <div class="field-hint">Start typing, then select a suggestion or keep a free text search.</div>
              </div>

              <div class="filter-field">
                <label>Advanced search</label>
                <div class="filter-inline" style="gap:6px;">
                  <select id="stMode">
                    <option value="include">Include</option>
                    <option value="exclude">Exclude</option>
                  </select>

                  <select id="stCmp">
                    <option value="ge">≥</option>
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
            </div>
          </details>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Date</strong>
                <span>Filter by RISM/source date range</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field">
                <label>Source date</label>
                <div class="filter-grid-2">
                  <input id="yearFrom" type="number" inputmode="numeric" placeholder="From (e.g. 1650)" />
                  <input id="yearTo" type="number" inputmode="numeric" placeholder="To (e.g. 1750)" />
                </div>
              </div>
            </div>
          </details>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Bibliography</strong>
                <span>Filter by catalogue reference</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field">
                <label>Match mode</label>
                <div class="filter-inline filter-mode-row">
                  <select id="bibMatchMode" aria-label="Bibliography matching mode">
                    <option value="any">Match any</option>
                    <option value="all">Match all</option>
                  </select>
                </div>
              </div>

              <div class="filter-field">
                <label>References</label>
                <div class="filter-dropdown-wrap">
                  <button id="bibToggle" type="button" class="wide-dropdown-toggle">All bibliographic references</button>
                  <div id="bibMenu" class="wide-dropdown-menu">
                    <div id="bibList"></div>
                  </div>
                </div>
                <div id="bibActive" class="active-filter-chips"></div>
              </div>
            </div>
          </details>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Holdings / Libraries</strong>
                <span>Filter by library sigla</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field">
                <label>Match mode</label>
                <div class="filter-inline filter-mode-row">
                  <select id="libraryMatchMode" aria-label="Holdings or libraries matching mode">
                    <option value="any">Match any</option>
                    <option value="all">Match all</option>
                  </select>
                </div>
              </div>

              <div class="filter-field" style="position:relative;">
                <label for="libraryInput">Sigla</label>
                <input id="libraryInput" type="text" placeholder="Type a library siglum: GB-Lbl, A-Wn…" autocomplete="off" />
                <div class="library-menu" id="libraryMenu">
                  <div class="library-list" id="libraryList"></div>
                </div>
                <div id="libraryActive" class="active-filter-chips"></div>
              </div>
            </div>
          </details>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Identifiers</strong>
                <span>Search exact catalogue identifiers</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field">
                <label for="rismNoInput">RISM number</label>
                <input id="rismNoInput" type="text" inputmode="numeric" placeholder="e.g. 990000327" />
              </div>
            </div>
          </details>

        </div>
      </div>
    </section>

    <section class="card">
      <div class="catalogue-head">
        <h2>Catalogue</h2>
        <div class="catalogue-sort">
          <label for="sortBy">Sort by</label>
          <select id="sortBy">
      <option value="composer">Composer A–Z</option>
      <option value="dateAsc">Source date ↑</option>
      <option value="dateDesc">Source date ↓</option>
          </select>
        </div>
      </div>
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
  const composerInput = document.getElementById('composerInput');
  const composerMenu = document.getElementById('composerMenu');
  const composerList = document.getElementById('composerList');

  const instrInput = document.getElementById('instrInput');
  const instrMenu = document.getElementById('instrMenu');
  const instrList = document.getElementById('instrList');
  const yearFrom = document.getElementById('yearFrom');
  const yearTo = document.getElementById('yearTo');
  const musicFilter = document.getElementById('musicFilter');
  const sourceFilter = document.getElementById('sourceFilter');
  const msDetailBlock = document.getElementById('msDetailBlock');
  const msDetailFilter = document.getElementById('msDetailFilter');
  const clearAllFilters = document.getElementById('clearAllFilters');

  const bibToggle = document.getElementById('bibToggle');
  const bibMenu = document.getElementById('bibMenu');
  const bibList = document.getElementById('bibList');
  const bibActive = document.getElementById('bibActive');
  const bibMatchMode = document.getElementById('bibMatchMode');

  const libraryInput = document.getElementById('libraryInput');
  const libraryMenu = document.getElementById('libraryMenu');
  const libraryList = document.getElementById('libraryList');
  const libraryActive = document.getElementById('libraryActive');
  const libraryMatchMode = document.getElementById('libraryMatchMode');

  const rismNoInput = document.getElementById('rismNoInput');
  const sortBy = document.getElementById('sortBy');

  const entriesContainer = document.getElementById('entries');
  const cards = Array.from(entriesContainer.querySelectorAll('.entry'));
  const noResults = document.getElementById('noResults');

  const resultCount = document.createElement('div');
  resultCount.id = 'resultCount';
  resultCount.style.margin = '0 0 10px';
  resultCount.style.fontSize = '0.86rem';
  resultCount.style.color = 'var(--muted)';
  resultCount.style.fontWeight = '600';
  entriesContainer.insertAdjacentElement('beforebegin', resultCount);

  function countVisibleSubpieces(card) {
    const lines = Array.from(card.querySelectorAll('.subpiece-line[data-pid]'));
    if (!lines.length) return 0;
    return lines.filter(ln => ln.style.display !== 'none').length;
  }

  function updateResultCount(visibleCards, matchingPieces, pieceLevelActive) {
    const entryWord = visibleCards === 1 ? 'entry' : 'entries';

    if (pieceLevelActive) {
      const pieceWord = matchingPieces === 1 ? 'piece' : 'pieces';
      resultCount.textContent = `${visibleCards} catalogue ${entryWord} shown · ${matchingPieces} matching ${pieceWord}`;
    } else {
      resultCount.textContent = `${visibleCards} catalogue ${entryWord} shown`;
    }
  }

  function normalize(s){ return (s || '').toLowerCase(); }
  function normalizeLoose(s){ return (s || '').toLowerCase().replace(/\\s+/g,' ').trim(); }
  function normalizeRismNo(s){ return (s || '').replace(/\\D+/g,''); }
  function parseIntSafe(x){
    const n = parseInt(x, 10);
    return Number.isFinite(n) ? n : null;
  }

  function parseJsonDataset(card, datasetKey, cacheKey){
    if(card[cacheKey]) return card[cacheKey];
    const raw = card.dataset[datasetKey] || '[]';
    try {
      card[cacheKey] = JSON.parse(raw);
    } catch(err) {
      card[cacheKey] = [];
    }
    return card[cacheKey];
  }

  function intersectsOrContains(values, selected, mode){
    if(!selected.length) return true;
    const valSet = new Set(values || []);
    if(mode === 'all'){
      return selected.every(v => valSet.has(v));
    }
    return selected.some(v => valSet.has(v));
  }

   // ============ Sort controls

  function compareDefault(a, b){
    const aa = parseIntSafe(a.dataset.sortDefault);
    const bb = parseIntSafe(b.dataset.sortDefault);
    return (aa ?? Number.MAX_SAFE_INTEGER) - (bb ?? Number.MAX_SAFE_INTEGER);
  }

  function compareText(a, b){
    return (a || '').localeCompare((b || ''), undefined, {sensitivity:'base'});
  }

  // Internal secondary sort only.
  // ZINKNET number stays the stable secondary order,
  // without appearing as a visible Sort by option.
  function compareZinknet(a, b){
    return compareDefault(a, b);
  }

  function compareComposer(a, b){
    const am = a.dataset.sortComposerMissing === '1';
    const bm = b.dataset.sortComposerMissing === '1';
    if(am !== bm) return am ? 1 : -1;

    const cmp = compareText(a.dataset.sortComposer || '', b.dataset.sortComposer || '');
    if(cmp !== 0) return cmp;

    return compareZinknet(a, b);
  }

  function compareDateAsc(a, b){
    const ay = parseIntSafe(a.dataset.sortYearStart);
    const by = parseIntSafe(b.dataset.sortYearStart);

    const am = ay === null;
    const bm = by === null;

    // Entries without date go last.
    if(am !== bm) return am ? 1 : -1;

    if(!am && ay !== by) return ay - by;

    // Same date: composer, then ZINKNET number.
    return compareComposer(a, b);
  }

  function compareDateDesc(a, b){
    const ay = parseIntSafe(a.dataset.sortYearEnd);
    const by = parseIntSafe(b.dataset.sortYearEnd);

    const am = ay === null;
    const bm = by === null;

    // Entries without date go last.
    if(am !== bm) return am ? 1 : -1;

    if(!am && ay !== by) return by - ay;

    // Same date: composer, then ZINKNET number.
    return compareComposer(a, b);
  }

  function applySort(){
    const mode = sortBy.value;
    const ordered = [...cards];

    if(mode === 'dateAsc'){
      ordered.sort(compareDateAsc);
    } else if(mode === 'dateDesc'){
      ordered.sort(compareDateDesc);
    } else {
      // Standard order: Composer A–Z, then ZINKNET number
      ordered.sort(compareComposer);
    }

    ordered.forEach(card => entriesContainer.appendChild(card));
  }

  sortBy.addEventListener('change', () => {
    applySort();
  });

  // ============ Composer dropdown
  const WORD_RE = /[A-Za-zÀ-ÖØ-öø-ÿ]+/g;
  function wordsOnly(s){ return (normalize(s).match(WORD_RE) || []); }

  const COMPOSERS = @@COMPOSERS@@;

  let composerSelected = "";

  function closeComposerMenu(){
    composerMenu.style.display = 'none';
    composerList.innerHTML = '';
  }

  function openComposerMenu(items){
    composerList.innerHTML = '';
    items.forEach(obj => {
      const div = document.createElement('div');
      div.className = 'composer-item';
      div.textContent = obj.d;
      div.addEventListener('click', () => {
        composerSelected = obj.d;
        composerInput.value = obj.d;
        closeComposerMenu();
        applyFilters();
      });
      composerList.appendChild(div);
    });
    composerMenu.style.display = items.length ? 'block' : 'none';
  }

  function computeComposerHits(){
    const qWords = wordsOnly(composerInput.value);
    if(!qWords.length) return [];
    const hits = [];
    for(const obj of COMPOSERS){
      const t = obj.t || '';
      let ok = true;
      for(const w of qWords){
        if(!t.includes(w)){ ok = false; break; }
      }
      if(ok){
        hits.push(obj);
        if(hits.length >= 25) break;
      }
    }
    return hits;
  }

  composerInput.addEventListener('input', () => {
    if(composerSelected && composerInput.value !== composerSelected){
      composerSelected = "";
      applyFilters();
    }
    const hits = computeComposerHits();
    if(!hits.length) closeComposerMenu();
    else openComposerMenu(hits);
  });

  composerInput.addEventListener('focus', () => {
    const hits = computeComposerHits();
    if(hits.length) openComposerMenu(hits);
  });

  // ============ Search Tool controls
  const stMode  = document.getElementById('stMode');
  const stCmp   = document.getElementById('stCmp');
  const stInstr = document.getElementById('stInstr');
  const stQty   = document.getElementById('stQty');
  const stAdd   = document.getElementById('stAdd');
  const stClear = document.getElementById('stClear');
  const stActive = document.getElementById('stActive');

  const SEARCH_TOOL_INSTRS = @@SEARCH_TOOL_INSTRS@@;
  const stRules = [];

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
      chip.textContent = `${sign} ${r.k} ${cmp} ${r.n} ×`;
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

  // ============ Contextual manuscript detail filter
  function updateMsDetailVisibility() {
    if (sourceFilter.value === 'Manuscript') {
      msDetailBlock.style.display = '';
    } else {
      msDetailFilter.value = '';
      msDetailBlock.style.display = 'none';
    }
  }

  // ============ Bibliography multi-select
  const BIBLIO_OPTIONS = @@BIBLIO_OPTIONS@@;
  const selectedBibliography = [];

  function shortLabel(text, maxLen=88){
    const s = text || '';
    return s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s;
  }

  function closeBibMenu(){
    bibMenu.style.display = 'none';
  }

  function openBibMenu(){
    bibMenu.style.display = 'block';
  }

  function toggleBibMenu(){
    if(bibMenu.style.display === 'block') closeBibMenu();
    else openBibMenu();
  }

  function renderBibliographyOptions(){
    bibList.innerHTML = '';
    BIBLIO_OPTIONS.forEach(ref => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'wide-dropdown-item';
      if(selectedBibliography.includes(ref)) btn.classList.add('is-selected');
      btn.textContent = ref;
      btn.title = ref;
      btn.addEventListener('click', () => {
        const idx = selectedBibliography.indexOf(ref);
        if(idx >= 0) selectedBibliography.splice(idx, 1);
        else selectedBibliography.push(ref);
        renderBibliographyOptions();
        renderBibliographyChips();
        applyFilters();
      });
      bibList.appendChild(btn);
    });
  }

  function renderBibliographyChips(){
    bibActive.innerHTML = '';
    selectedBibliography.forEach(ref => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'active-filter-chip';
      chip.title = `Click to remove: ${ref}`;

      const text = document.createElement('span');
      text.className = 'chip-text';
      text.textContent = shortLabel(ref, 62);

      const x = document.createElement('span');
      x.textContent = '×';

      chip.appendChild(text);
      chip.appendChild(x);
      chip.addEventListener('click', () => {
        const idx = selectedBibliography.indexOf(ref);
        if(idx >= 0) selectedBibliography.splice(idx, 1);
        renderBibliographyOptions();
        renderBibliographyChips();
        applyFilters();
      });
      bibActive.appendChild(chip);
    });

    if(selectedBibliography.length){
      bibToggle.textContent = `${selectedBibliography.length} bibliographic reference${selectedBibliography.length===1?'':'s'} selected`;
    } else {
      bibToggle.textContent = 'All bibliographic references';
    }
  }

  bibToggle.addEventListener('click', toggleBibMenu);
  bibMatchMode.addEventListener('change', applyFilters);

  renderBibliographyOptions();
  renderBibliographyChips();

  // ============ Holdings / Libraries multi-select
  const LIBRARY_OPTIONS = @@LIBRARY_OPTIONS@@;
  const LIBRARY_DISPLAY = new Map(LIBRARY_OPTIONS.map(o => [o.k, o.d]));
  const selectedLibraries = [];

  function closeLibraryMenu(){
    libraryMenu.style.display = 'none';
    libraryList.innerHTML = '';
  }

  function openLibraryMenu(items){
    libraryList.innerHTML = '';
    items.forEach(obj => {
      const div = document.createElement('div');
      div.className = 'library-item';
      div.textContent = obj.d;
      div.title = obj.d;
      div.addEventListener('click', () => {
        if(!selectedLibraries.includes(obj.k)){
          selectedLibraries.push(obj.k);
        }
        libraryInput.value = '';
        closeLibraryMenu();
        renderLibraryChips();
        applyFilters();
      });
      libraryList.appendChild(div);
    });
    libraryMenu.style.display = items.length ? 'block' : 'none';
  }

  function computeLibraryHits(){
    const q = normalizeLoose(libraryInput.value);
    if(!q) return [];
    const hits = [];
    for(const obj of LIBRARY_OPTIONS){
      const display = normalizeLoose(obj.d);
      const key = normalizeLoose(obj.k);
      if(display.includes(q) || key.includes(q)){
        hits.push(obj);
        if(hits.length >= 40) break;
      }
    }
    return hits;
  }

  function renderLibraryChips(){
    libraryActive.innerHTML = '';
    selectedLibraries.forEach(k => {
      const display = LIBRARY_DISPLAY.get(k) || k;
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'active-filter-chip';
      chip.title = `Click to remove: ${display}`;

      const text = document.createElement('span');
      text.className = 'chip-text';
      text.textContent = display;

      const x = document.createElement('span');
      x.textContent = '×';

      chip.appendChild(text);
      chip.appendChild(x);
      chip.addEventListener('click', () => {
        const idx = selectedLibraries.indexOf(k);
        if(idx >= 0) selectedLibraries.splice(idx, 1);
        renderLibraryChips();
        applyFilters();
      });
      libraryActive.appendChild(chip);
    });
  }

  libraryInput.addEventListener('input', () => {
    const hits = computeLibraryHits();
    if(!hits.length) closeLibraryMenu();
    else openLibraryMenu(hits);
  });

  libraryInput.addEventListener('focus', () => {
    const hits = computeLibraryHits();
    if(hits.length) openLibraryMenu(hits);
  });

  libraryMatchMode.addEventListener('change', applyFilters);

  // ============ Organology link filter
  // Supported URL fragments:
  //   index.html#org=IDENTIFIER
  //   index.html#organology=IDENTIFIER
  //
  // This works because the Organology column is already included
  // in data-search / Global search.
  const orgFilterBadge = document.createElement('div');
  orgFilterBadge.id = 'orgFilterBadge';
  orgFilterBadge.style.display = 'none';
  orgFilterBadge.style.margin = '0 0 10px';
  orgFilterBadge.style.fontSize = '0.86rem';
  orgFilterBadge.style.color = 'var(--violet-text)';
  orgFilterBadge.style.fontWeight = '600';
  orgFilterBadge.style.cursor = 'pointer';

  entriesContainer.insertAdjacentElement('beforebegin', orgFilterBadge);

  function readOrgFilterFromHash() {
    const raw = (window.location.hash || '').replace(/^#/, '');
    if (!raw) return '';

    const params = new URLSearchParams(raw);
    return params.get('org') || params.get('organology') || '';
  }

  function clearOrgHash() {
    if (window.location.hash) {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  function applyOrgFilterFromHash() {
    const orgId = readOrgFilterFromHash();

    if (!orgId) {
      orgFilterBadge.style.display = 'none';
      orgFilterBadge.textContent = '';
      return;
    }

    searchInput.value = orgId;

    orgFilterBadge.style.display = '';
    orgFilterBadge.innerHTML = `Organology link filter: <strong>${orgId}</strong> ×`;
    orgFilterBadge.title = 'Click to clear this Organology link filter';
  }

  orgFilterBadge.addEventListener('click', () => {
    clearOrgHash();
    searchInput.value = '';
    orgFilterBadge.style.display = 'none';
    orgFilterBadge.textContent = '';
    applyFilters();
  });

  window.addEventListener('hashchange', () => {
    applyOrgFilterFromHash();
    applyFilters();
  });

  applyOrgFilterFromHash();

  // ============ Clear all filters
  function clearAllFiltersFn() {
    searchInput.value = '';

    composerInput.value = '';
    composerSelected = '';
    closeComposerMenu();

    instrInput.value = '';
    yearFrom.value = '';
    yearTo.value = '';

    musicFilter.value = '';
    sourceFilter.value = '';
    msDetailFilter.value = '';
    updateMsDetailVisibility();

    selectedBibliography.length = 0;
    bibMatchMode.value = 'any';
    closeBibMenu();
    renderBibliographyOptions();
    renderBibliographyChips();

    selectedLibraries.length = 0;
    libraryMatchMode.value = 'any';
    libraryInput.value = '';
    closeLibraryMenu();
    renderLibraryChips();

    rismNoInput.value = '';

    clearOrgHash();
    orgFilterBadge.style.display = 'none';
    orgFilterBadge.textContent = '';

    stRules.length = 0;
    renderStRules();

    cards.forEach(card => {
      applyCollectionView(card, null);
    });

    applyFilters();
  }

  clearAllFilters.addEventListener('click', clearAllFiltersFn);

  // ============ Existing parsers per card
  function parseSearchToolPieces(card){
    if(card.__stPieces) return card.__stPieces;

    const raw = card.dataset.stoolPieces || '';
    const pieces = [];
    if(raw){
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

  // ============ New JSON parsers per card
  function parseBiblioPieces(card){
    return parseJsonDataset(card, 'biblioPieces', '__biblioPieces');
  }

  function parseLibraryPieces(card){
    return parseJsonDataset(card, 'libraryPieces', '__libraryPieces');
  }

  function parseRismNumberPieces(card){
    return parseJsonDataset(card, 'rismPieces', '__rismPieces');
  }

  // ============ Matching logic: Search Tool
  function ruleOk(val, rule){
    const n = rule.n;
    const cmp = rule.cmp;
    if(rule.mode === 'include'){
      if(cmp === 'eq') return (val === n);
      return (val >= n);
    } else {
      if(cmp === 'eq') return (val !== n);
      return (val < n);
    }
  }

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

      if(okPiece) matchPids.add(p.pid);
    }

    return {ok: matchPids.size > 0, matchPids};
  }

  // ============ Matching logic: Year filter
  function overlapsYearRange(rmin, rmax, fromY, toY){
    if(fromY !== null && rmax < fromY) return false;
    if(toY   !== null && rmin > toY)   return false;
    return true;
  }

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

  // ============ Matching logic: Bibliography
  function matchesBibliographyFilter(card){
    if(!selectedBibliography.length) return {ok:true, matchPids:new Set()};

    const mode = bibMatchMode.value || 'any';
    const pieces = parseBiblioPieces(card);
    if(!pieces.length) return {ok:false, matchPids:new Set()};

    const matchPids = new Set();
    for(const p of pieces){
      const values = p.values || [];
      if(intersectsOrContains(values, selectedBibliography, mode)){
        matchPids.add(p.pid);
      }
    }

    return {ok: matchPids.size > 0, matchPids};
  }

  // ============ Matching logic: Holdings / Libraries
  function matchesLibraryFilter(card){
    if(!selectedLibraries.length) return {ok:true, matchPids:new Set()};

    const mode = libraryMatchMode.value || 'any';
    const pieces = parseLibraryPieces(card);
    if(!pieces.length) return {ok:false, matchPids:new Set()};

    const matchPids = new Set();
    for(const p of pieces){
      const values = p.values || [];
      if(intersectsOrContains(values, selectedLibraries, mode)){
        matchPids.add(p.pid);
      }
    }

    return {ok: matchPids.size > 0, matchPids};
  }

  // ============ Matching logic: RISM number
  function matchesRismNumberFilter(card){
    const query = normalizeRismNo(rismNoInput.value);
    if(!query) return {ok:true, matchPids:new Set()};

    const pieces = parseRismNumberPieces(card);
    if(!pieces.length) return {ok:false, matchPids:new Set()};

    const matchPids = new Set();
    for(const p of pieces){
      const values = p.values || [];
      const okPiece = values.some(v => normalizeRismNo(v).includes(query));
      if(okPiece) matchPids.add(p.pid);
    }

    return {ok: matchPids.size > 0, matchPids};
  }

  // ============ Composer match set
  function composerMatchSet(card){
    if(!composerSelected) return {ok:true, matchPids:null};

    const clist = (card.dataset.composers || '').split('||').filter(Boolean);
    const hasAny = clist.includes(composerSelected);
    if(!hasAny) return {ok:false, matchPids:new Set()};

    const lines = Array.from(card.querySelectorAll('.subpiece-line[data-pid]'));
    if(!lines.length){
      return {ok:true, matchPids:null};
    }

    const hits = new Set();
    const all = new Set();
    lines.forEach(ln => {
      const pid = ln.dataset.pid || '';
      if(pid) all.add(pid);
      const c = (ln.dataset.composerRaw || '').trim();
      if(pid && c === composerSelected) hits.add(pid);
    });

    if(hits.size > 0){
      return {ok:true, matchPids:hits};
    }

    const headerC = (card.dataset.composerRaw || '').trim();
    if(headerC === composerSelected){
      return {ok:true, matchPids:all};
    }

    return {ok:false, matchPids:new Set()};
  }

  // ============ Highlight + smart collection view
  function applyCollectionView(card, showSet){
    const lines = Array.from(card.querySelectorAll('.subpiece-line[data-pid]'));
    if(!lines.length) return;

    const badge = card.querySelector('.subpieces-matchcount');

    if(!showSet){
      lines.forEach(ln => {
        ln.classList.remove('is-match');
        ln.style.display = '';
      });
      if(badge) badge.textContent = '';
      return;
    }

    let count = 0;
    lines.forEach(ln => {
      const pid = ln.dataset.pid || '';
      const hit = pid && showSet.has(pid);
      ln.classList.toggle('is-match', !!hit);
      ln.style.display = hit ? '' : 'none';
      if(hit) count++;
    });

    if(badge){
      badge.textContent = count ? `• ${count} match${count===1?'':'es'}` : '';
    }
  }

  // ============ Populate basic filters
  const musicSet = new Set();
  const sourceCategorySet = new Set();
  const msDetailSet = new Set();

  cards.forEach(card => {
    (card.dataset.musicTypes || '').split('||').filter(Boolean).forEach(v => musicSet.add(v));
    (card.dataset.sourceCategories || '').split('||').filter(Boolean).forEach(v => sourceCategorySet.add(v));
    (card.dataset.msDetails || '').split('||').filter(Boolean).forEach(v => msDetailSet.add(v));
  });

  const musicOrder = {
    'Instrumental': 1,
    'Vocal / Mixed': 2,
  };

  Array.from(musicSet).sort((a,b) => {
    const aa = musicOrder[a] || 99;
    const bb = musicOrder[b] || 99;
    return aa === bb ? a.localeCompare(b) : aa - bb;
  }).forEach(v => {
    const o=document.createElement('option'); o.value=v; o.textContent=v; musicFilter.appendChild(o);
  });

  const sourceCategoryOrder = {
    'Manuscript': 1,
    'Print': 2,
    'Text': 3,
  };

  Array.from(sourceCategorySet).sort((a,b) => {
    const aa = sourceCategoryOrder[a] || 99;
    const bb = sourceCategoryOrder[b] || 99;
    return aa === bb ? a.localeCompare(b) : aa - bb;
  }).forEach(v => {
    const o=document.createElement('option'); o.value=v; o.textContent=v; sourceFilter.appendChild(o);
  });

  const msDetailOrder = {
    'Ms.': 1,
    'Ms. Autograph': 2,
    'Ms. Copy': 3,
  };

  Array.from(msDetailSet).sort((a,b) => {
    const aa = msDetailOrder[a] || 99;
    const bb = msDetailOrder[b] || 99;
    return aa === bb ? a.localeCompare(b) : aa - bb;
  }).forEach(v => {
    const o=document.createElement('option'); o.value=v; o.textContent=v; msDetailFilter.appendChild(o);
  });

  updateMsDetailVisibility();

  // ============ Main filter
  function applyFilters() {
    const q  = normalize(searchInput.value);
    const qi = normalize(instrInput.value);
    const mt = musicFilter.value;
    const st = sourceFilter.value;
    const msd = msDetailFilter.value;

    let visible = 0;
    let matchingPieces = 0;

    const stActiveOn = stRules.length > 0;
    const yrActiveOn = (parseIntSafe(yearFrom.value) !== null) || (parseIntSafe(yearTo.value) !== null);
    const compActiveOn = !!composerSelected;
    const bibActiveOn = selectedBibliography.length > 0;
    const libraryActiveOn = selectedLibraries.length > 0;
    const rismActiveOn = !!normalizeRismNo(rismNoInput.value);

    const pieceLevelActive =
      stActiveOn ||
      yrActiveOn ||
      compActiveOn ||
      bibActiveOn ||
      libraryActiveOn ||
      rismActiveOn;

    cards.forEach(card => {
      const text  = normalize(card.dataset.search);
      const instr = normalize(card.dataset.instr);
      const mts = (card.dataset.musicTypes || '').split('||').filter(Boolean);
      const sourceCats = (card.dataset.sourceCategories || '').split('||').filter(Boolean);
      const msDetails = (card.dataset.msDetails || '').split('||').filter(Boolean);

      let ok = true;
      if (q  && !text.includes(q)) ok = false;
      if (qi && !instr.includes(qi)) ok = false;
      if (mt && !mts.includes(mt)) ok = false;
      if (st && !sourceCats.includes(st)) ok = false;
      if (msd && !msDetails.includes(msd)) ok = false;

      const compMatch = composerMatchSet(card);
      if(ok && !compMatch.ok) ok = false;

      let stMatch = {ok:true, matchPids:new Set()};
      if(ok){
        stMatch = matchesSearchTool(card);
        if(!stMatch.ok) ok = false;
      }

      let yrMatch = {ok:true, matchPids:new Set()};
      if(ok){
        yrMatch = matchesYearFilter(card);
        if(!yrMatch.ok) ok = false;
      }

      let bibMatch = {ok:true, matchPids:new Set()};
      if(ok){
        bibMatch = matchesBibliographyFilter(card);
        if(!bibMatch.ok) ok = false;
      }

      let libraryMatch = {ok:true, matchPids:new Set()};
      if(ok){
        libraryMatch = matchesLibraryFilter(card);
        if(!libraryMatch.ok) ok = false;
      }

      let rismMatch = {ok:true, matchPids:new Set()};
      if(ok){
        rismMatch = matchesRismNumberFilter(card);
        if(!rismMatch.ok) ok = false;
      }

      let showSet = null;
      const hasLines = card.querySelector('.subpiece-line[data-pid]') !== null;

      if(hasLines && ok && pieceLevelActive){
        const sets = [];
        if(compActiveOn && compMatch.matchPids) sets.push(compMatch.matchPids);
        if(stActiveOn) sets.push(stMatch.matchPids);
        if(yrActiveOn) sets.push(yrMatch.matchPids);
        if(bibActiveOn) sets.push(bibMatch.matchPids);
        if(libraryActiveOn) sets.push(libraryMatch.matchPids);
        if(rismActiveOn) sets.push(rismMatch.matchPids);

        if(sets.length){
          showSet = new Set(sets[0]);
          for(let i=1;i<sets.length;i++){
            const next = sets[i];
            showSet.forEach(pid => { if(!next.has(pid)) showSet.delete(pid); });
          }
          if(showSet.size === 0) ok = false;
        }
      }

      card.style.display = ok ? '' : 'none';

      if (ok) visible++;

      if (ok) {
        applyCollectionView(card, showSet);

        if (pieceLevelActive) {
          const subpieceCount = countVisibleSubpieces(card);
          matchingPieces += subpieceCount ? subpieceCount : 1;
        }
      } else {
        applyCollectionView(card, null);
      }
    });

    noResults.style.display = visible ? 'none' : '';
    updateResultCount(visible, matchingPieces, pieceLevelActive);
  }

  // ============ Listeners
  searchInput.addEventListener('input', applyFilters);
  instrInput.addEventListener('input', applyFilters);
  yearFrom.addEventListener('input', applyFilters);
  yearTo.addEventListener('input', applyFilters);
  musicFilter.addEventListener('change', applyFilters);
  sourceFilter.addEventListener('change', () => {
    updateMsDetailVisibility();
    applyFilters();
  });
  msDetailFilter.addEventListener('change', applyFilters);
  rismNoInput.addEventListener('input', applyFilters);

  document.addEventListener('click', (ev) => {
    if(!composerMenu.contains(ev.target) && ev.target !== composerInput){
      closeComposerMenu();
    }
    if(instrMenu && !instrMenu.contains(ev.target) && ev.target !== instrInput){
      closeInstrMenu();
    }
    if(!libraryMenu.contains(ev.target) && ev.target !== libraryInput){
      closeLibraryMenu();
    }
    if(!bibMenu.contains(ev.target) && ev.target !== bibToggle){
      closeBibMenu();
    }
  });

  applySort();
  applyFilters();
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
  <link rel="stylesheet" href="style.css?v=source-aware-2026-05-29">
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
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (OUT_DIR / "style.css").write_text(style_css, encoding="utf-8")

    assets_dir = OUT_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if (ASSETS_SRC / HEM_LOGO).exists():
        shutil.copy(ASSETS_SRC / HEM_LOGO, assets_dir / HEM_LOGO)
    if (ASSETS_SRC / RISM_LOGO).exists():
        shutil.copy(ASSETS_SRC / RISM_LOGO, assets_dir / RISM_LOGO)

    df = pd.read_csv(SHEET_CSV_URL, dtype={COL_RISM_NO: "string"})
    df.columns = [str(c).replace("\r\n", "\n").strip() for c in df.columns]

    df["__sort_key"] = df[COL_ZINK].apply(parse_zinknet)
    df["__group"] = df[COL_ZINK].apply(group_id)
    df_sorted = df.sort_values("__sort_key").reset_index(drop=True)

    groups = {}
    for _, row in df_sorted.iterrows():
        zid = clean_str(get_col(row, COL_ZINK))
        if not zid:
            continue
        gid = row["__group"]
        groups.setdefault(gid, []).append(zid)
    for gid, ids in groups.items():
        ids.sort(key=parse_zinknet)
    group_sizes = {gid: len(ids) for gid, ids in groups.items()}

    records = {}
    for _, row in df_sorted.iterrows():
        zid = clean_str(get_col(row, COL_ZINK))
        if not zid:
            continue

        gid = row["__group"]
        gcount = group_sizes.get(gid, 1)

        rec = {
            "id": zid,
            "group": gid,
            "group_count": int(gcount),
            "indiv_coll": clean_str(get_col(row, COL_INDIV)),
            "composer_raw": clean_str(get_col(row, COL_COMP)),
            "title_raw": clean_str(get_col(row, COL_TITLE)),
            "concordances_raw": clean_str(get_col(row, COL_CONC)),
            "instr_rism_main_raw": clean_str(get_col(row, COL_INSTR_MAIN)),
            "instr_rism_alt_raw": clean_str(get_col(row, COL_INSTR_ALT)),
            "instr_catalogs_raw": clean_str(get_col(row, COL_INSTR_CAT)),
            "music_type_raw": norm_music_type(get_col(row, COL_MUSIC_TYPE)),
            "source_type_raw": clean_str(get_col(row, COL_SOURCE_TYPE)),
            "rism_no_raw": clean_numberish(get_col(row, COL_RISM_NO)),
            "rism_link_raw": clean_str(get_col(row, COL_RISM_LINK)),
            "category_raw": clean_str(get_col(row, COL_CATEGORY)),
            "note_raw": clean_str(get_col(row, COL_NOTE)),
            "bibliography_raw": clean_str(get_col(row, COL_BIB)),
            "organology_raw": clean_str(get_col(row, COL_ORG)),
            "search_tool_raw": clean_str(get_col(row, COL_SEARCH_TOOL)),

            "rism_holdings_raw": clean_str(get_col(row, COL_RISM_HOLDINGS)) if (COL_RISM_HOLDINGS in df.columns) else "",
            "rism_date_raw": clean_str(get_col(row, COL_RISM_DATE)) if (COL_RISM_DATE in df.columns) else "",
            "rism_earliest_year_raw": clean_numberish(get_col(row, COL_RISM_EARLIEST)) if (COL_RISM_EARLIEST in df.columns) else "",
            "rism_latest_year_raw": clean_numberish(get_col(row, COL_RISM_LATEST)) if (COL_RISM_LATEST in df.columns) else "",
        }

        lib_raw = get_col(row, COL_LIB)
        shelf_raw = get_col(row, COL_SHELF)
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

        rec["search_scenarios"] = parse_search_tool_to_scenarios(rec["search_tool_raw"], limit=256)
        rec["year_min"] = parse_int_safe(rec["rism_earliest_year_raw"])
        rec["year_max"] = parse_int_safe(rec["rism_latest_year_raw"])
        rec["bibliography_refs"] = bibliography_refs(rec["bibliography_raw"])
        rec["holdings_library_sigla_raw"] = holdings_libraries_sigla(
            rec["rism_holdings_raw"],
            rec["library_raw"]
        )
        rec["holdings_library_sigla_keys"] = [s.casefold() for s in rec["holdings_library_sigla_raw"]]

        records[zid] = rec

    for rec in records.values():
        rec["concordances_ids"] = [cid for cid in parse_conc_ids(rec["concordances_raw"]) if cid in records]

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
                "search_tool_raw": "", "search_scenarios": [],
                "rism_holdings_raw": "", "rism_date_raw": "",
                "rism_earliest_year_raw": "", "rism_latest_year_raw": "",
                "year_min": None, "year_max": None,
                "bibliography_refs": [],
                "holdings_library_sigla_raw": [],
                "holdings_library_sigla_keys": [],
            }

    # Global Search Tool instrument index
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

    # Composer dropdown index
    composer_set = sorted(
        {records[z]["composer_raw"] for z in records if records[z].get("composer_raw")},
        key=lambda s: s.lower()
    )
    composers_js = json.dumps(
        [{"d": c, "t": composer_tokens(c)} for c in composer_set],
        ensure_ascii=False
    )

    # Bibliography options
    bibliography_options = sorted(
        {ref for rec in records.values() for ref in rec.get("bibliography_refs", [])},
        key=lambda s: s.casefold()
    )
    bibliography_options_js = json.dumps(bibliography_options, ensure_ascii=False)

    # Holdings / libraries options
    # Dedupe case-insensitively while preserving a preferred display form.
    library_display_by_key = {}
    for rec in records.values():
        for raw_siglum in rec.get("holdings_library_sigla_raw", []):
            key = raw_siglum.casefold()
            library_display_by_key.setdefault(key, raw_siglum)

    library_options = [
        {"k": k, "d": d}
        for k, d in sorted(library_display_by_key.items(), key=lambda kv: kv[1].casefold())
    ]
    library_options_js = json.dumps(library_options, ensure_ascii=False)

    # =========================
    # INDEX BUILD
    # =========================
    group_html_parts = []
    sorted_group_ids = sorted(groups.keys(), key=lambda g: parse_zinknet(g))

    for default_order_idx, gid in enumerate(sorted_group_ids):
        ids = groups[gid]
        coll_id = next((z for z in ids if records.get(z, {}).get("indiv_coll") == "Coll."), None)
        is_virtual_collection = gid in virtual_headers

        header_id = coll_id if coll_id else (gid if is_virtual_collection else ids[0])
        hrec = records[header_id]
        gcount_total = len(ids)

        used_links_tags = set()

        # Index card tags
        tags_left_html = []
        tags_right_html = []

        if hrec.get("music_type_raw"):
            tags_left_html.append(f'<span class="tag tag-type">{escape_textnode(hrec["music_type_raw"])}</span>')
        if hrec.get("source_type_raw"):
            tags_left_html.append(f'<span class="tag tag-source">{escape_textnode(hrec["source_type_raw"])}</span>')

        if hrec.get("concordances_ids"):
            n = len(hrec["concordances_ids"])
            tags_left_html.append(f'<span class="tag tag-conc">{n} concordance{"s" if n != 1 else ""}</span>')

        if not is_virtual_collection:
            chip = rism_chip_self(hrec, used_links_tags)
            if chip:
                tags_left_html.append(chip)

        if coll_id or is_virtual_collection:
            nb_pieces = gcount_total - 1 if coll_id else gcount_total
            nb_pieces = max(nb_pieces, 0)
            tags_right_html.append(f'<span class="tag tag-count">{nb_pieces} piece{"s" if nb_pieces != 1 else ""}</span>')

        # Index card typography
        rism_dates = sorted({
            clean_str(records[z].get("rism_date_raw", "")).strip()
            for z in ids
            if clean_str(records[z].get("rism_date_raw", "")).strip()
        })

        date_chip = ""
        if len(rism_dates) == 1:
            date_chip = (
                f'<span class="tag" '
                f'style="font-size:0.68rem; padding:2px 7px; margin-right:6px; '
                f'background:#ffffff; border-color:#d7daee; color:#6b7280; '
                f'letter-spacing:0; text-transform:none; font-weight:500;">'
                f'{escape_textnode(rism_dates[0])}</span>'
            )
        elif len(rism_dates) >= 2:
            date_chip = (
                f'<span class="tag" '
                f'style="font-size:0.68rem; padding:2px 7px; margin-right:6px; '
                f'background:#ffffff; border-color:#d7daee; color:#6b7280; '
                f'letter-spacing:0; text-transform:none; font-weight:500;">'
                f'multiple</span>'
            )

        group_recs = [records[z] for z in ids if z in records]
        primary_label_raw = index_primary_label_raw(hrec, group_recs)
        composer_txt = escape_textnode(primary_label_raw) if primary_label_raw else ""
        display_id = header_id.split("/", 1)[0] if (coll_id and "/" in header_id) else header_id

        line_ids = [z for z in ids if not (coll_id and z == coll_id)]

        source_panel_html = build_index_source_panel(hrec, group_recs)

        if coll_id or is_virtual_collection:
            sub_lines = []
            for pid in line_ids:
                r = records[pid]

                conc_tag = ""
                if r["concordances_ids"]:
                    n = len(r["concordances_ids"])
                    conc_tag = f'<span class="tag tag-conc">{n} concordance{"s" if n!=1 else ""}</span>'

                content_title = abbreviated_title_html(r["title_raw"] or "(Untitled)", max_len=92)
                content_composer = r["composer"] or "Anonymous"
                content_instr = index_instrumentation_html(r)

                extras = []
                if conc_tag:
                    extras.append(conc_tag)

                sub_lines.append(f"""
              <div class="index-content-row subpiece-line" data-pid="{escape_attr(pid)}" data-composer-raw="{escape_attr(r.get('composer_raw',''))}">
                <div><span class="index-piece-ref">{escape_textnode(pid)}</span></div>
                <div>
                  <div class="index-content-title">{content_title}</div>
                  <div class="index-content-meta">{content_composer}</div>
                  <div class="index-content-instr">{content_instr}</div>
                  {('<div class="index-content-extra">' + ''.join(extras) + '</div>') if extras else ''}
                </div>
              </div>""")

            left_panel_html = f"""
          <div class="index-contents-panel">
            <div class="index-panel-title">CONTENTS <span class="subpieces-matchcount"></span></div>
            {''.join(sub_lines)}
          </div>"""
        else:
            work_title = abbreviated_title_html(hrec["title_raw"] or "(Untitled)", max_len=92)
            work_meta = hrec["composer"] or ""
            work_instr = index_instrumentation_html(hrec)

            left_panel_html = f"""
          <div class="index-work-panel">
            <div class="index-panel-title">WORK</div>
            <div class="index-work-title">{work_title}</div>
            {f'<div class="index-work-meta">{work_meta}</div>' if work_meta else ''}
            <div class="index-instr-integrated">
              <span class="index-instr-label">Instrumentation</span>
              <div class="index-instr-text">{work_instr or '<span class="muted-value">—</span>'}</div>
            </div>
          </div>"""

        body_panel_html = f"""
        <div class="index-card-grid">
          {left_panel_html}
          {source_panel_html}
        </div>"""

        title_raw_header = hrec["title_raw"]
        if primary_label_raw and clean_str(title_raw_header).casefold() == clean_str(primary_label_raw).casefold():
            title_html = ""
        else:
            title_html = hrec["title"] if hrec["title"] else ("" if is_virtual_collection else "<em>(Untitled)</em>")

        if title_html:
            title_line_html = f"""
          <div class="entry-title-line" style="display:flex; align-items:center; flex-wrap:wrap; gap:0; margin-top:2px; color:#374151; font-size:0.92rem; font-weight:500; line-height:1.25;">
            {date_chip}<span>{title_html}</span>
          </div>"""
        elif date_chip:
            title_line_html = f"""
          <div class="entry-title-line" style="display:flex; align-items:center; flex-wrap:wrap; gap:0; margin-top:2px; color:#374151; font-size:0.92rem; font-weight:500; line-height:1.25;">
            {date_chip}
          </div>"""
        else:
            title_line_html = ""

        # Full-text search blob
        search_blob_parts = []
        for z in ids:
            rr = records[z]
            search_blob_parts.extend([
                z, rr["composer_raw"], rr["title_raw"],
                rr["instr_rism_main_raw"], rr["instr_rism_alt_raw"], rr["instr_catalogs_raw"],
                rr["library_raw"], rr["shelfmark_raw"],
                rr["music_type_raw"], rr["source_type_raw"],
                rr["note_raw"], rr["organology_raw"],
                rr["rism_no_raw"],
                rr["bibliography_raw"],
                rr.get("rism_date_raw",""),
                rr.get("rism_holdings_raw",""),
            ])
        search_blob = " ".join([p for p in search_blob_parts if p]).replace("\n", " ")

        # Music type filter values
        music_types_for_filter = set()
        for z in ids:
            mt = records[z]["music_type_raw"]
            if not mt:
                continue
            if mt == "Instrumental / Vocal / Mixed":
                music_types_for_filter.add("Instrumental")
                music_types_for_filter.add("Vocal / Mixed")
            else:
                music_types_for_filter.add(mt)

        music_type_order = {
            "Instrumental": 1,
            "Vocal / Mixed": 2,
        }

        music_types_set = sorted(
            music_types_for_filter,
            key=lambda x: (music_type_order.get(x, 99), x.lower())
        )

        # Source category + manuscript detail filters
        source_categories_for_group = set()
        ms_details_for_group = set()

        for z in ids:
            st_raw = records[z]["source_type_raw"]
            source_categories_for_group.update(source_categories_for_filter(st_raw))
            ms_details_for_group.update(manuscript_details_for_filter(st_raw))

        source_category_order = {
            "Manuscript": 1,
            "Print": 2,
            "Text": 3,
        }

        ms_detail_order = {
            "Ms.": 1,
            "Ms. Autograph": 2,
            "Ms. Copy": 3,
        }

        source_categories_set = sorted(
            source_categories_for_group,
            key=lambda x: (source_category_order.get(x, 99), x.lower())
        )

        ms_details_set = sorted(
            ms_details_for_group,
            key=lambda x: (ms_detail_order.get(x, 99), x.lower())
        )

        instr_blob = " ".join(
            ((records[z]["instr_rism_main_raw"] + " " + records[z]["instr_rism_alt_raw"] + " " + records[z]["instr_catalogs_raw"]).strip())
            for z in ids
        ).replace("\n", " ")

        composers_set = sorted(
            {records[z].get("composer_raw", "") for z in ids if records[z].get("composer_raw", "")},
            key=lambda x: x.lower()
        )
        composers_blob = "||".join(composers_set)

        line_ids = [z for z in ids if not (coll_id and z == coll_id)]

        # Search Tool per-piece dataset
        piece_chunks = []
        for z in line_ids if (coll_id or is_virtual_collection) else [header_id]:
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

        # Year per-piece dataset
        yr_chunks = []
        if coll_id or is_virtual_collection:
            year_ids = list(line_ids)
            hymin = hrec.get("year_min", None)
            hymax = hrec.get("year_max", None)
            if hymin is not None and hymax is not None:
                yr_chunks.append(f"__HEADER__@@{hymin}:{hymax}")
        else:
            year_ids = [header_id]

        for z in year_ids:
            rr = records[z]
            ymin = rr.get("year_min", None)
            ymax = rr.get("year_max", None)
            if ymin is None or ymax is None:
                yr_chunks.append(f"{z}@@")
            else:
                yr_chunks.append(f"{z}@@{ymin}:{ymax}")

        yr_pieces_blob = "##".join(yr_chunks)

        # New piece-level JSON datasets
        header_for_json = hrec if (coll_id or is_virtual_collection) else None
        data_piece_ids = line_ids if (coll_id or is_virtual_collection) else [header_id]

        biblio_payload = piece_value_payload(
            records,
            data_piece_ids,
            lambda rr: rr.get("bibliography_refs", []),
            header_rec=header_for_json,
        )
        library_payload = piece_value_payload(
            records,
            data_piece_ids,
            lambda rr: rr.get("holdings_library_sigla_keys", []),
            header_rec=header_for_json,
        )
        rism_payload = piece_value_payload(
            records,
            data_piece_ids,
            lambda rr: [rr["rism_no_raw"]] if rr.get("rism_no_raw") else [],
            header_rec=header_for_json,
        )

        # Sort metadata
        sort_composer_raw = hrec.get("composer_raw", "")
        if not sort_composer_raw:
            group_composers = sorted(
                {records[z].get("composer_raw", "") for z in ids if records[z].get("composer_raw", "")},
                key=lambda s: s.casefold()
            )
            if len(group_composers) == 1:
                sort_composer_raw = group_composers[0]

        sort_composer_missing = "0" if sort_composer_raw else "1"

        h_year_min = hrec.get("year_min", None)
        h_year_max = hrec.get("year_max", None)
        group_year_mins = [records[z].get("year_min") for z in ids if records[z].get("year_min") is not None]
        group_year_maxs = [records[z].get("year_max") for z in ids if records[z].get("year_max") is not None]

        sort_year_start = h_year_min if h_year_min is not None else (min(group_year_mins) if group_year_mins else "")
        sort_year_end = h_year_max if h_year_max is not None else (max(group_year_maxs) if group_year_maxs else "")

        open_link_label = "Open collection page" if (coll_id or is_virtual_collection) else "Open single-work page"
        open_link_html = f'<div class="entry-open-link"><a href="piece-{header_id.replace("/","-")}.html" target="_blank" rel="noopener">{open_link_label}</a></div>'

        group_html_parts.append(f"""
    <details class="entry"
      data-search="{escape_attr(search_blob)}"
      data-composer-raw="{escape_attr(hrec.get('composer_raw',''))}"
      data-composers="{escape_attr(composers_blob)}"
      data-music-types="{escape_attr('||'.join(music_types_set))}"
      data-source-categories="{escape_attr('||'.join(source_categories_set))}"
      data-ms-details="{escape_attr('||'.join(ms_details_set))}"
      data-instr="{escape_attr(instr_blob)}"
      data-stool-pieces="{escape_attr(stool_pieces_blob)}"
      data-yr-pieces="{escape_attr(yr_pieces_blob)}"
      data-biblio-pieces="{json_attr(biblio_payload)}"
      data-library-pieces="{json_attr(library_payload)}"
      data-rism-pieces="{json_attr(rism_payload)}"
      data-sort-default="{default_order_idx}"
      data-sort-composer="{escape_attr(sort_composer_raw)}"
      data-sort-composer-missing="{sort_composer_missing}"
      data-sort-year-start="{escape_attr(sort_year_start)}"
      data-sort-year-end="{escape_attr(sort_year_end)}">
      <summary>
        <div class="entry-main" style="width:100%; min-width:0;">
          <div class="entry-heading-line" style="display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; min-width:0;">
            <span class="entry-ref" style="font-size:0.72rem; color:#6b7280; font-weight:600; letter-spacing:.04em; line-height:1.1; flex:0 0 auto;">
              {escape_textnode(display_id)}
            </span>
            <span class="entry-composer-main" style="font-size:1.05rem; font-weight:750; color:#020617; line-height:1.15; min-width:0;">
              {composer_txt}
            </span>
          </div>

          {title_line_html}

          <div class="entry-tags" style="display:flex; justify-content:space-between; align-items:center; gap:8px; width:100%; margin-top:6px;">
            <div class="entry-tags-left" style="display:flex; flex-wrap:wrap; gap:4px; align-items:center; min-width:0;">
              {''.join(tags_left_html)}
            </div>
            <div class="entry-tags-right" style="display:flex; flex-wrap:wrap; gap:4px; align-items:center; justify-content:flex-end; margin-left:auto;">
              {''.join(tags_right_html)}
            </div>
          </div>
        </div>
        <div class="entry-arrow">›</div>
      </summary>
      <div class="entry-body">
        {body_panel_html}
        {open_link_html}
      </div>
    </details>
    """)

    entries_html = "\n".join(group_html_parts)

    (OUT_DIR / "index.html").write_text(
        index_template
        .replace("@@HEADER@@", build_header_html())
        .replace("@@ENTRIES@@", entries_html)
        .replace("@@SEARCH_TOOL_INSTRS@@", search_tool_js)
        .replace("@@COMPOSERS@@", composers_js)
        .replace("@@BIBLIO_OPTIONS@@", bibliography_options_js)
        .replace("@@LIBRARY_OPTIONS@@", library_options_js),
        encoding="utf-8"
    )

    # =========================
    # DETAIL PAGES
    # =========================
    for zid, rec in records.items():
        used_links_page = set()

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

        tags = []
        if rec["music_type_raw"]:
            tags.append(f'<span class="tag tag-type">{escape_textnode(rec["music_type_raw"])}</span>')
        if rec["source_type_raw"]:
            tags.append(f'<span class="tag tag-source">{escape_textnode(rec["source_type_raw"])}</span>')
        if rec["concordances_ids"]:
            n = len(rec["concordances_ids"])
            tags.append(f'<span class="tag tag-conc">{n} concordance{"s" if n!=1 else ""}</span>')

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

            kv_rows = []
            if rism_date:
                kv_rows.append(f'<div class="k">Date</div><div class="v">{escape_textnode(rism_date)}</div>')
            if rism_holdings:
                kv_rows.append(f'<div class="k">Holdings</div><div class="v">{holdings_list_html(rism_holdings)}</div>')

            rism_drawer = f"""
    <details class="rism"{open_attr}>
      <summary>
        <div class="rism-left">
          <span class="rism-title">RISM</span>
          <div class="rism-mini">{pills_html}</div>
        </div>
      </summary>
      <div class="rism-body">
        <div class="rism-kv">
          {''.join(kv_rows)}
        </div>
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
                stt = cr["source_type_raw"]
                mt_tag = f'<span class="tag tag-type">{escape_textnode(mt)}</span>' if mt else ""
                st_tag = f'<span class="tag tag-source">{escape_textnode(stt)}</span>' if stt else ""
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
    print("Composers indexed:", len(composer_set))
    print("Bibliography references indexed:", len(bibliography_options))
    print("Holdings / Libraries sigla indexed:", len(library_options))

if __name__ == "__main__":
    main()
