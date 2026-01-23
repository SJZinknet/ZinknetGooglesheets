# generator/build.py
import os, re, html, shutil
from pathlib import Path
import pandas as pd

# =========================
# CONFIG
# =========================
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1XrARBpah9CL_BMj3XRsyw1CL5o8RVheDyuAg5ya0z4I/gviz/tq?tqx=out:csv&sheet=NEW%20MERGED%20FILE"

OUT_DIR = Path("docs")          # GitHub Pages can publish /docs
ASSETS_SRC = Path("assets_src") # put hem.png + rism.png here
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
# HELPERS (from your script)
# =========================
def clean_str(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

def clean_numberish(val):
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
    t = clean_str(s)
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t.strip())
    CANON = {"Instrumental", "Vocal / Mixed", "Instrumental / Vocal / Mixed"}
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

def build_header_html():
    hem_img = f'<img class="hem-logo" src="assets/{HEM_LOGO}" alt="HEM – Haute école de musique de Genève">' if (OUT_DIR/"assets"/HEM_LOGO).exists() else '<span class="logo-fallback">HEM</span>'
    rism_img = f'<img class="rism-logo" src="assets/{RISM_LOGO}" alt="RISM">' if (OUT_DIR/"assets"/RISM_LOGO).exists() else '<span class="logo-fallback logo-fallback--small">RISM</span>'
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
      {hem_img}
      <div class="collab-line">
        <span>In collaboration with</span>
        {rism_img}
      </div>
    </div>
  </div>
</header>
"""

# --- CSS: keep exactly as in your generator (shortened here? no: keep full) ---
style_css = r"""<
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
.filters input[type="text"] {
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
.filter-inline { display:flex; gap:8px; flex-wrap:wrap; }

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
.subpieces-title { font-size:0.78rem; text-transform:uppercase; letter-spacing:.13em; color:var(--muted); margin-bottom:4px; }
.subpiece-line {
  padding:6px 0; border-top:1px solid #d8ddf5;
  font-size:0.88rem; display:flex; flex-direction:column; gap:2px;
}
.subpiece-line:first-of-type { border-top:none; }
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
>"""

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

def main():
    # clean output
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # .nojekyll to keep GitHub Pages fully static
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # write CSS
    (OUT_DIR / "style.css").write_text(style_css, encoding="utf-8")

    # copy assets
    assets_dir = OUT_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if (ASSETS_SRC / HEM_LOGO).exists():
        shutil.copy(ASSETS_SRC / HEM_LOGO, assets_dir / HEM_LOGO)
    if (ASSETS_SRC / RISM_LOGO).exists():
        shutil.copy(ASSETS_SRC / RISM_LOGO, assets_dir / RISM_LOGO)

    # read sheet CSV
    df = pd.read_csv(SHEET_CSV_URL, dtype={"RISM No.": "string"})
    df["__sort_key"] = df["ZINKNET NO."].apply(parse_zinknet)
    df["__group"] = df["ZINKNET NO."].apply(group_id)
    df_sorted = df.sort_values("__sort_key").reset_index(drop=True)

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

        records[zid] = rec

    for rec in records.values():
        rec["concordances_ids"] = [cid for cid in parse_conc_ids(rec["concordances_raw"]) if cid in records]

    # virtual collections (same logic as yours)
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
            }

    # =========================
    # BUILD INDEX + DETAIL PAGES
    # (keep your templates, unchanged)
    # =========================
    # NOTE: to keep this message manageable, you should paste your existing
    # index_template + detail_template blocks here, exactly as-is, and write
    # them into OUT_DIR the same way you already do.

    raise SystemExit(
        "build.py skeleton ready: now paste (1) your full style_css and "
        "(2) the index/detail page generation blocks into this file."
    )

if __name__ == "__main__":
    main()
