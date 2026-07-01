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
# - RISM edition information for prints: Publisher / Printer + Publication Place.
# - v15 display fix: dropdown layering + instrumentation simple-search suggestions.
# - v20 responsive cleanup: compact centered header + mobile Search Tool layout.
# - v21 mobile filter panel: hamburger in header opens filters under sticky header.
# - v22 Organology: dedicated multi-code instrument filter + URL hash support.
# - v23 browseable dropdowns: show available options on focus for organology, holdings and instrumentation.
# - v24 collection /0 fix, filter-text cleanup, and instrument lexicon labels/tooltips.
# - v25 case-sensitive instrumentation codes: A/a, S/s, T/t, B/b stay distinct. Organology is not treated as instrumentation.

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
COL_RISM_PUBLISHER_PRINTER = "RISM Publisher / Printer"
COL_RISM_PUBLICATION_PLACE = "RISM Publication Place"

# Instrument lexicon imported from Lexique work in progress.xlsx (v24).
# Most lexicon keys are casefolded, but v25 adds case-sensitive overrides for
# ZinkNET instrumentation codes where uppercase/lowercase carry different meanings.
INSTRUMENT_DISPLAY_LABELS = {
    "a": "Alto voice",
    "b": "Bass voice",
    "b ad lib": "Bass instrument (ad libitum)",
    "bariton": "Bariton voice",
    "bassetto": "Bassetto",
    "bc": "Basso continuo",
    "bc: arp": "Basso continuo (arpa)",
    "bc: org": "Basso continuo (organo)",
    "bc: regal": "Basso continuo (regal)",
    "bombarde": "Bombarde",
    "cap": "Capella",
    "cap 1": "Capella 1",
    "cap 2": "Capella 2",
    "cap 3": "Capella 3",
    "cap 4": "Capella 4",
    "cap ad lib": "Capella ad libitum",
    "cap fiducinii": "Capella fiducinii",
    "cap with instruments": "Capella with instruments",
    "coro 1 cap": "Coro 1 capella",
    "coro 1 conc": "Coro 1 concerto",
    "coro 1 instr": "Coro 1 instrumentale",
    "coro 1 rip": "Coro 1 ripieno",
    "coro angelici cap": "Coro angelici Capella",
    "coro inf": "Coro inferiori",
    "coro instr": "Coro instrumenti",
    "coro sup": "Coro superiori",
    "coro voc": "Coro vocale",
    "rip": "Ripieno",
    "rip ad lib": "Ripieno ad libitum",
    "rit": "Ritornello",
    "sinf": "Sinfonia"
}

INSTRUMENT_SEARCH_LABELS = {
    "a": "Alto voice",
    "arp": "Arpa",
    "b": "Bass voice",
    "bagpipe": "Bagpipe",
    "bariton": "Bariton voice",
    "bassetto": "Bassetto",
    "bc": "Basso continuo",
    "bombarde": "Bombarde",
    "cemb": "Cembalo",
    "cetra": "Cetra",
    "ciaramella": "Ciaramella",
    "cimb": "Cimbalum",
    "cl": "Clarinet",
    "clno": "Clarino",
    "cnto": "Cornetto",
    "cnto muto": "Cornetto muto",
    "colascione": "Colascione",
    "cor": "Cor",
    "cor da caccia": "Cor da Caccia",
    "cor di bassetto": "Cor di Bassetto",
    "cornettino": "Cornettino",
    "crummhorn": "Crummhorn",
    "dolzaine": "Dolzaine",
    "fag": "Fagotto",
    "fag.picc": "Fagotto piccolo",
    "fiffaro": "Fiffaro",
    "fl": "Flauto",
    "i": "Instrumento",
    "lira": "Lira",
    "lirone": "Lirone",
    "lituus": "Lituus",
    "lute": "Lute",
    "mandoline": "Mandoline",
    "ob": "Oboe",
    "org": "Organo",
    "pf": "Pianoforte",
    "pipe and tabor": "Pipe and Tabor",
    "recorder": "Recorder",
    "regal": "Regal",
    "ribecchino": "Ribecchino",
    "s": "Soprano voice",
    "salterio": "Salterio",
    "schryari": "Schryari",
    "serpent": "Serpent",
    "sordun": "Sordun",
    "spinetta": "Spinetta",
    "strings": "Strings",
    "t": "Tenor voice",
    "tamb": "Tamburro",
    "tb": "Tuba",
    "tenorete": "Tenorete",
    "theorbe": "Theorbe",
    "timp": "Timpanum",
    "tr": "Trumpet",
    "trb": "Trombone",
    "v": "Voice",
    "v 5": "Fifth voice",
    "v/i": "Voice or Instrument",
    "vihuela": "Vihuela",
    "violetta": "Violetta",
    "vl": "Violino",
    "vla": "Viola",
    "vla da gamba": "Viola da Gamba",
    "vlc": "Violoncello",
    "vlne": "Violone",
    "winds": "Winds"
}

# Case-sensitive overrides for instrumentation/Search Tool codes.
# These codes are intentionally NOT normalized with casefold():
# uppercase = voice; lowercase = instrument.
CASE_SENSITIVE_INSTRUMENT_SEARCH_LABELS = {
    "S": "Soprano voice",
    "s": "Soprano instrument",
    "A": "Alto voice",
    "a": "Alto instrument",
    "T": "Tenor voice",
    "t": "Tenor instrument",
    "B": "Bass voice",
    "b": "Bass instrument",
}

CASE_SENSITIVE_INSTRUMENT_DISPLAY_LABELS = {
    "S": "Soprano voice",
    "s": "Soprano instrument",
    "A": "Alto voice",
    "a": "Alto instrument",
    "T": "Tenor voice",
    "t": "Tenor instrument",
    "B": "Bass voice",
    "b": "Bass instrument",
}

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

def norm_indiv_coll_marker(raw):
    s = clean_str(raw).strip().casefold()
    s = s.rstrip(".").strip()
    return s

def is_collection_marker(raw):
    return norm_indiv_coll_marker(raw) == "coll"

def is_collection_id(zid):
    return clean_str(zid).endswith("/0")

def is_real_collection_record(rec):
    return is_collection_marker(rec.get("indiv_coll", "")) or is_collection_id(rec.get("id", ""))

def instrument_search_label(code):
    code = clean_str(code)
    if not code:
        return ""

    # v25: exact-case lookup first. A/a, S/s, T/t, B/b are distinct
    # in ZinkNET instrumentation and Search Tool data.
    if code in CASE_SENSITIVE_INSTRUMENT_SEARCH_LABELS:
        return CASE_SENSITIVE_INSTRUMENT_SEARCH_LABELS[code]

    return INSTRUMENT_SEARCH_LABELS.get(code.casefold(), "")

def instrument_display_label(code):
    code = clean_str(code)
    if not code:
        return ""

    # v25: exact-case lookup first for documentary instrumentation.
    if code in CASE_SENSITIVE_INSTRUMENT_DISPLAY_LABELS:
        return CASE_SENSITIVE_INSTRUMENT_DISPLAY_LABELS[code]

    return INSTRUMENT_DISPLAY_LABELS.get(code.casefold(), "")

def instrument_search_display(code):
    code = clean_str(code)
    if not code:
        return ""
    label = instrument_search_label(code)
    return f"{label} ({code})" if label else code

def instrument_search_terms_from_scenarios(scenarios):
    terms = []
    for sc in scenarios or []:
        for k in sc.keys():
            terms.append(k)
            label = instrument_search_label(k)
            if label:
                terms.append(label)
                terms.append(instrument_search_display(k))
    return " ".join(unique_preserve_order([t for t in terms if t]))

_INSTRUMENT_DISPLAY_PATTERN = None

def escape_instrument_codes_with_tooltips(text):
    """
    Escape text for HTML while wrapping recognized instrument codes in
    tooltip spans. Unknown codes remain untouched.
    """
    global _INSTRUMENT_DISPLAY_PATTERN

    s = clean_str(text)
    if not s:
        return ""

    if not INSTRUMENT_DISPLAY_LABELS:
        return html.escape(s, quote=False).replace("\n", "<br>")

    if _INSTRUMENT_DISPLAY_PATTERN is None:
        keys = sorted(
            set(INSTRUMENT_DISPLAY_LABELS.keys()) | set(CASE_SENSITIVE_INSTRUMENT_DISPLAY_LABELS.keys()),
            key=len,
            reverse=True
        )
        if not keys:
            return html.escape(s, quote=False).replace("\n", "<br>")
        # Avoid matching inside longer alpha-numeric / dotted / colon / hyphenated codes.
        # v25: deliberately case-sensitive, because A and a are different codes.
        _INSTRUMENT_DISPLAY_PATTERN = re.compile(
            r'(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9_.:-])('
            + "|".join(re.escape(k) for k in keys)
            + r')(?![A-Za-zÀ-ÖØ-öø-ÿ0-9_.:-])'
        )

    parts = []
    last = 0
    for m in _INSTRUMENT_DISPLAY_PATTERN.finditer(s):
        parts.append(html.escape(s[last:m.start()], quote=False))
        token = m.group(0)
        label = instrument_display_label(token)
        if label:
            parts.append(
                f'<span class="instr-code" title="{escape_attr(label)}">{html.escape(token, quote=False)}</span>'
            )
        else:
            parts.append(html.escape(token, quote=False))
        last = m.end()

    parts.append(html.escape(s[last:], quote=False))
    return "".join(parts).replace("\n", "<br>")

def format_uniform_instr_content(raw_text):
    """
    Format uniform instrumentation content wherever it is displayed.

    Rules:
      - LABEL: { ... } becomes its own line, with braces removed:
            Cap: {V (5), vl (2)}  ->  Cap: V (5), vl (2)
      - { ... } without a label also becomes its own line, with braces removed.
      - Any remaining material outside braces is preserved and placed on a clean line
        when it follows or precedes brace groups.

    Examples:
      {S (2), A (1)}, Cap: {V (5)}, trb (2)
      ->
      S (2), A (1)
      Cap: V (5)
      trb (2)

    This returns only formatted HTML content, without adding a section heading.
    """
    s = clean_str(raw_text)
    if not s:
        return ""

    def repl_labeled(m):
        label = m.group(1).strip().strip(",; ")
        content = m.group(2).strip()
        return f"\n{label} {content}\n"

    def repl_unlabeled(m):
        content = m.group(1).strip()
        return f"\n{content}\n"

    # First preserve labels immediately attached to a brace group.
    t2 = re.sub(r'([^{}\n\r,;]+:\s*)\{([^{}]*)\}', repl_labeled, s)

    # Then isolate any remaining brace group without a label.
    t2 = re.sub(r'\{([^{}]*)\}', repl_unlabeled, t2)

    # Clean separators around line breaks created by the brace expansion.
    t2 = re.sub(r'\s*[,;]\s*\n', '\n', t2)
    t2 = re.sub(r'\n\s*[,;]\s*', '\n', t2)
    t2 = re.sub(r'\n+', '\n', t2).strip(' \n,;')
    if not t2.strip():
        return ""

    return escape_instrument_codes_with_tooltips(t2)


def format_uniform_instr(raw_text, alternative=False):
    """
    Legacy full block formatter.
    Kept for older index/detail blocks, now using the same content formatter
    as the v10/v12 rendering.
    """
    body = format_uniform_instr_content(raw_text)
    if not body:
        return ""

    heading = "UNIFORM INSTRUMENTATION (ALTERNATIVE)" if alternative else "UNIFORM INSTRUMENTATION"
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

def organology_codes(raw):
    """
    Parse the Organology column as a list of instrument codes.

    Recommended Google Sheet syntax:
      cnto; trb; fag

    Also accepted for convenience:
      - one code per line
      - comma-separated codes in simple cases

    Display spelling is preserved for chips/options, while filtering uses
    case-insensitive keys. The raw Organology cell is still displayed on
    detail pages as documentary text.
    """
    s = clean_str(raw)
    if not s:
        return []

    out = []
    seen = set()
    for part in re.split(r"[;\r\n,]+", s):
        code = re.sub(r"\s+", " ", part).strip()
        code = code.strip("[](){} ")
        if not code:
            continue
        key = code.casefold()
        if key not in seen:
            seen.add(key)
            out.append(code)
    return out

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
      <div class="brand-row">
        <button id="mobileFilterToggle" class="mobile-filter-toggle" type="button" aria-label="Open filters" aria-controls="mobileFilterPanel" aria-expanded="false">
          <span></span><span></span><span></span>
        </button>
        <h1>ZinkNET</h1>
      </div>
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
  /* Must stay above filter sections and their floating menus. */
  z-index:1000;
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


/* Header — compact tablet/mobile variants.
   The full project metadata is useful on desktop, but too tall on smaller screens. */
@media (max-width: 980px){
  header.app-header{
    padding:7px 12px 6px;
  }

  .header-grid{
    grid-template-columns:minmax(0,1fr) auto;
    align-items:center;
    gap:10px;
  }

  .header-grid .left{
    min-width:0;
  }

  h1{
    font-size:1.55rem;
  }

  .tagline{
    margin-top:1px;
    font-size:.82rem;
    line-height:1.15;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
  }

  .meta-line{
    display:none;
  }

  .right{
    min-width:auto;
    align-items:center;
    justify-content:flex-end;
    gap:0;
    padding-top:0;
  }

  .partner-text{
    display:none;
  }

  .logo-column{
    flex-direction:row;
    align-items:center;
    gap:7px;
  }

  .hem-logo{
    height:42px;
  }

  .rism-logo{
    height:22px;
  }

  .logo-fallback{
    padding:4px 8px;
    font-size:.74rem;
  }

  .logo-fallback--small{
    padding:3px 7px;
    font-size:.70rem;
  }
}

@media (max-width: 700px){
  header.app-header{
    padding:6px 10px 5px;
  }

  h1{
    font-size:1.36rem;
  }

  .tagline{
    font-size:.75rem;
  }

  .hem-logo{
    height:34px;
  }

  .rism-logo{
    height:20px;
  }

  .logo-column{
    gap:6px;
  }
}

@media (max-width: 480px){
  h1{
    font-size:1.30rem;
  }

  .tagline{
    display:none;
  }

  .hem-logo{
    height:30px;
  }

  .rism-logo{
    height:18px;
  }

  .logo-column{
    gap:5px;
  }
}



/* Mobile filter trigger.
   Hidden with display:none by default, so it occupies no space on desktop
   and on detail pages. */
.brand-row{
  display:flex;
  align-items:center;
  gap:8px;
  min-width:0;
}

.mobile-filter-toggle{
  display:none;
  width:34px;
  height:34px;
  flex:0 0 auto;
  align-items:center;
  justify-content:center;
  flex-direction:column;
  gap:4px;
  border:1px solid var(--border-subtle);
  border-radius:999px;
  background:#ffffff;
  color:#111827;
  box-shadow:0 6px 16px rgba(15,23,42,0.07);
  cursor:pointer;
  padding:0;
}

.mobile-filter-toggle span{
  display:block;
  width:15px;
  height:2px;
  border-radius:999px;
  background:#111827;
}

.mobile-filter-toggle:hover{
  border-color:var(--border-strong);
  background:#fafaff;
}

.mobile-filter-close{
  display:none;
  width:32px;
  height:32px;
  flex:0 0 auto;
  align-items:center;
  justify-content:center;
  border-radius:999px;
  border:1px solid var(--border-subtle);
  background:#ffffff;
  color:#374151;
  font-size:1.3rem;
  line-height:1;
  cursor:pointer;
}

.search-card-actions{
  display:flex;
  align-items:center;
  justify-content:flex-end;
  gap:8px;
  flex:0 0 auto;
}

/* Header — v20 vertical centering refinements */
@media (max-width: 980px){
  .header-grid{
    align-items:center;
  }

  .header-grid .left{
    min-width:0;
    display:flex;
    flex-direction:column;
    justify-content:center;
  }

  .right{
    align-self:center;
    align-items:center;
  }

  .logo-column,
  .hem-slot,
  .rism-slot{
    align-items:center;
    justify-content:center;
  }
}

@media (max-width: 700px){
  header.app-header{
    min-height:46px;
  }

  .header-grid{
    align-items:center;
  }

  h1{
    display:flex;
    align-items:center;
  }

  .right{
    min-height:36px;
  }
}

@media (max-width: 480px){
  header.app-header{
    min-height:42px;
  }

  .right{
    min-height:32px;
  }
}

/* Mobile Search Tool — more accessible controls */
@media (max-width: 700px){
  body.index-page .search-tool-field{
    border:1px solid rgba(208,213,235,0.85);
    background:linear-gradient(180deg,#ffffff,#fbfcff);
    border-radius:14px;
    padding:10px;
  }

  body.index-page .search-tool-controls{
    display:grid !important;
    grid-template-columns:1.2fr .75fr .75fr;
    gap:8px !important;
    align-items:stretch;
  }

  body.index-page .search-tool-controls select,
  body.index-page .search-tool-controls button{
    width:100%;
    min-width:0;
    min-height:38px;
    border-radius:12px;
    font-size:.86rem;
  }

  body.index-page .search-tool-controls #stMode{
    grid-column:1;
  }

  body.index-page .search-tool-controls #stCmp{
    grid-column:2;
  }

  body.index-page .search-tool-controls #stQty{
    grid-column:3;
  }

  body.index-page .search-tool-controls #stInstr{
    grid-column:1 / -1;
  }

  body.index-page .search-tool-controls #stAdd{
    grid-column:1 / 3;
    display:flex;
    align-items:center;
    justify-content:center;
    font-weight:700;
  }

  body.index-page .search-tool-controls #stClear{
    grid-column:3;
    display:flex;
    align-items:center;
    justify-content:center;
  }

  body.index-page #stActive{
    margin-top:9px !important;
    gap:7px !important;
  }

  body.index-page #stActive .tag{
    padding:5px 9px;
    font-size:.76rem;
    border-radius:999px;
  }

  body.index-page .search-tool-hint{
    margin-top:7px;
  }
}

@media (max-width: 480px){
  body.index-page .search-tool-controls{
    grid-template-columns:1fr 1fr;
  }

  body.index-page .search-tool-controls #stMode{
    grid-column:1;
  }

  body.index-page .search-tool-controls #stCmp{
    grid-column:2;
  }

  body.index-page .search-tool-controls #stInstr{
    grid-column:1 / -1;
  }

  body.index-page .search-tool-controls #stQty{
    grid-column:1;
  }

  body.index-page .search-tool-controls #stAdd{
    grid-column:2;
  }

  body.index-page .search-tool-controls #stClear{
    grid-column:1 / -1;
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
  /* Above closed filter sections, but still below the sticky header. */
  z-index:20;
  background:#ffffff;
  border-color:var(--border-strong);
  box-shadow:0 8px 22px rgba(15,23,42,0.07);
}

/* Active floating menus must rise above the following filter sections,
   but the whole filter stack must remain below the sticky header. */
details.filter-section.dropdown-active{
  z-index:200;
}

details.filter-section.dropdown-active .composer-list,
details.filter-section.dropdown-active .instr-list,
details.filter-section.dropdown-active .wide-dropdown-menu,
details.filter-section.dropdown-active .library-list,
details.filter-section.dropdown-active .organology-list{
  z-index:220;
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
  max-height:260px;
  overflow:auto;
  z-index:30;
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

.instr-item.is-selected{
  background:rgba(139,92,246,0.10);
  color:var(--violet-text);
  font-weight:650;
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
  z-index:30;
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

.library-menu,
.organology-menu{
  display:none;
  position:relative;
}

.library-menu .library-list,
.organology-menu .organology-list{
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
  z-index:30;
  padding:6px;
}

.library-item,
.organology-item{
  padding:7px 10px;
  border-radius:12px;
  cursor:pointer;
  font-size:0.9rem;
  color:var(--text);
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:10px;
}

.library-item:hover,
.organology-item:hover{
  background: rgba(35,75,184,0.06);
}

.library-item.is-selected,
.organology-item.is-selected{
  background:rgba(139,92,246,0.10);
  color:var(--violet-text);
  font-weight:650;
}

.choice-item-label{
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.choice-item-count{
  color:#6b7280;
  font-size:.8rem;
  white-space:nowrap;
  font-weight:500;
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

.instr-code {
  text-decoration: underline dotted rgba(80,90,130,.45);
  text-underline-offset: 2px;
  cursor: help;
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

.index-instr-variants{
  display:grid;
  gap:3px;
}

.index-instr-variant{
  display:grid;
  grid-template-columns:minmax(108px,125px) minmax(0,1fr);
  gap:7px;
  align-items:start;
}

.index-instr-variant-label{
  color:#53618a;
  font-size:.68rem;
  text-transform:uppercase;
  letter-spacing:.10em;
  font-weight:750;
  line-height:1.25;
  white-space:nowrap;
}

.index-instr-variant-content{
  min-width:0;
  overflow-wrap:anywhere;
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

.index-source-note{
  color:#6b7280;
  font-size:.76rem;
  line-height:1.25;
}

.index-source-identity{
  font-size:.94rem;
  font-weight:600;
  color:var(--muted);
  letter-spacing:.01em;
  line-height:1.18;
}

.index-soft-ref{
  font-size:.70rem;
  color:#8a91a0;
  font-weight:600;
  letter-spacing:.035em;
  line-height:1.1;
}

.source-shelfmark{
  font-size:.84rem;
  color:#1f2937;
  font-weight:500;
  letter-spacing:0;
  line-height:1.25;
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


/* Index page — tablet/mobile normal flow.
   Below the desktop-app breakpoint, avoid nested column scrolls and let the page scroll naturally. */
@media (max-width: 1099px){
  body.index-page{
    overflow:auto;
  }

  body.index-page .shell{
    max-width:none;
    margin:0;
    padding:12px 14px 22px;
  }

  body.index-page .layout{
    grid-template-columns:1fr;
    gap:14px;
  }

  body.index-page .search-card,
  body.index-page .catalogue-card{
    height:auto;
    min-height:0;
    display:block;
  }

  body.index-page .filters{
    overflow:visible;
    padding-right:0;
    margin-right:0;
  }

  body.index-page .entries{
    max-height:none;
    overflow:visible;
    padding-right:0;
  }
}

@media (max-width: 700px){
  body.index-page .shell{
    padding:10px 10px 18px;
  }

  .card{
    border-radius:16px;
    padding:12px;
  }

  .search-card-header{
    align-items:center;
  }

  .clear-top-btn{
    padding:4px 8px !important;
  }

  .catalogue-head{
    align-items:flex-start;
    flex-direction:column;
  }

  .catalogue-sort{
    width:100%;
    justify-content:flex-start;
  }
}


/* Mobile filter panel — variant B:
   full-width panel below the sticky header, opened from the header hamburger. */
@media (max-width: 700px){
  body.index-page .mobile-filter-toggle{
    display:inline-flex;
  }

  body.index-page .header-grid .left{
    flex-direction:column;
    align-items:flex-start;
  }

  body.index-page .brand-row{
    align-items:center;
  }

  body.index-page .search-card{
    display:none;
    position:fixed;
    left:0;
    right:0;
    top:var(--index-header-height, 52px);
    bottom:0;
    z-index:950;
    border-radius:0;
    border-left:none;
    border-right:none;
    border-bottom:none;
    padding:12px;
    overflow:hidden;
    flex-direction:column;
    box-shadow:0 22px 50px rgba(15,23,42,0.22);
  }

  body.index-page.filters-open{
    overflow:hidden;
  }

  body.index-page.filters-open .search-card{
    display:flex;
  }

  body.index-page .search-card-header{
    flex:0 0 auto;
    border-bottom:1px solid rgba(208,213,235,0.72);
    padding-bottom:10px;
    margin-bottom:10px;
  }

  body.index-page .search-card-actions{
    margin-left:auto;
  }

  body.index-page .mobile-filter-close{
    display:inline-flex;
  }

  body.index-page .filters{
    flex:1 1 auto;
    min-height:0;
    overflow-y:auto;
    overflow-x:visible;
    padding-right:2px;
    padding-bottom:18px;
    overscroll-behavior:contain;
  }

  body.index-page .layout{
    display:block;
  }

  body.index-page .catalogue-card{
    display:block;
  }
}

@media (max-width: 480px){
  body.index-page .mobile-filter-toggle{
    width:32px;
    height:32px;
  }

  body.index-page .mobile-filter-toggle span{
    width:14px;
  }

  body.index-page .search-card{
    padding:10px;
  }
}

/* =========================
   Index page — v22 responsive layout
   App layout remains desktop-only. Tablet/mobile return to normal page flow.
   ========================= */
@media (min-width: 1100px){
  body.index-page{
    overflow:hidden;
  }

  body.index-page .shell{
    max-width:1800px;
    height:calc(100vh - var(--index-header-height, 104px));
    min-height:560px;
    margin-left:clamp(16px, 3vw, 64px);
    margin-right:clamp(16px, 3vw, 64px);
    padding:14px 0 16px;
  }

  body.index-page .layout{
    height:100%;
    min-height:0;
    grid-template-columns:minmax(280px,340px) minmax(0,1fr);
    align-items:stretch;
  }

  body.index-page .search-card,
  body.index-page .catalogue-card{
    height:100%;
    min-height:0;
    display:flex;
    flex-direction:column;
  }

  body.index-page .search-card{
    overflow:visible;
  }

  body.index-page .filters{
    flex:1 1 auto;
    min-height:0;
    overflow-y:auto;
    overflow-x:visible;
    padding-right:4px;
    margin-right:-4px;
    overscroll-behavior:contain;
  }

  body.index-page .catalogue-head,
  body.index-page #resultCount,
  body.index-page #orgFilterBadge{
    flex:0 0 auto;
  }

  body.index-page .entries{
    flex:1 1 auto;
    min-height:0;
    max-height:none;
    overflow:auto;
    overscroll-behavior:contain;
  }

  /* In app layout the filter column is scrollable. Floating menus therefore
     switch to fixed positioning so that Bibliography and suggestions are not
     clipped by the scroll container. They remain below the sticky header. */
  body.index-page .wide-dropdown-menu.is-fixed-menu,
  body.index-page .composer-list.is-fixed-menu,
  body.index-page .instr-list.is-fixed-menu,
  body.index-page .library-list.is-fixed-menu,
  body.index-page .organology-list.is-fixed-menu{
    position:fixed;
    right:auto;
    bottom:auto;
    z-index:900;
    max-width:calc(100vw - 24px);
  }

  body.index-page .wide-dropdown-menu.is-fixed-menu{
    width:min(760px, calc(100vw - 24px));
  }
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
  z-index:30;
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
/* =========================
   Detail pages — v10 architecture
   ========================= */
.detail-shell-v10{max-width:1260px;margin:0 auto;padding:18px 22px 34px;}
.detail-page-v10{background:rgba(255,255,255,.78);border:1px solid var(--border-subtle);border-radius:24px;padding:15px;box-shadow:0 18px 44px rgba(15,23,42,.09);}
.detail-topline-v10{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:4px 4px 12px;border-bottom:1px solid #dbe0f2;margin-bottom:12px;}
.detail-ref-v10{color:#111827;font-size:.95rem;font-weight:650;letter-spacing:.02em;}
.detail-columns-v10{display:grid;grid-template-columns:minmax(0,1fr) minmax(240px,310px);gap:12px;align-items:start;}
.detail-left-stack-v10,.detail-right-stack-v10{display:flex;flex-direction:column;gap:10px;min-width:0;align-self:start;}
.detail-lower-left-v10{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;align-items:start;}
.detail-lower-left-v10 > .full-span{grid-column:1 / -1;}
.detail-panel-v10,.detail-doc-v10{border:1px solid #d4d9ef;background:#fff;border-radius:18px;padding:12px 14px;min-width:0;}
.detail-main-panel-v10{background:linear-gradient(180deg,#ffffff,#f8f9ff);}
.detail-doc-v10{overflow:hidden;padding:0;}
.detail-panel-title-v10{font-size:.72rem;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-weight:780;margin-bottom:10px;}
.detail-identity-v10{margin:0 0 8px;}.detail-identity-label-v10{font-size:.70rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);font-weight:760;margin-bottom:3px;}
.detail-identity-value-v10{font-size:1.12rem;font-weight:800;color:#020617;line-height:1.18;}
.detail-identity-value-v10.source-identity{font-size:.96rem;font-weight:560;color:#4b5563;}
.detail-soft-rule-v10{height:1px;background:#e1e5f5;margin:10px 0;}
.detail-title-full-v10{font-size:1rem;font-weight:500;color:#1f2937;line-height:1.32;overflow-wrap:anywhere;}
.detail-instr-v10{margin-top:10px;border-top:1px solid #e1e5f5;padding-top:9px;color:#1f2937;font-size:.91rem;line-height:1.38;overflow-wrap:anywhere;}
.detail-instr-label-v10,.detail-content-title-label-v10{display:block;font-size:.70rem;text-transform:uppercase;letter-spacing:.12em;color:#25345f;font-weight:760;margin-bottom:4px;}
.detail-instr-variants-v10{display:flex;flex-direction:column;gap:8px;}
.detail-instr-variant-v10{display:grid;grid-template-columns:minmax(0,88px) minmax(0,1fr);gap:10px;align-items:start;}
.detail-instr-variant-label-v10{font-size:.68rem;text-transform:uppercase;letter-spacing:.11em;color:var(--muted);font-weight:760;line-height:1.25;}
.detail-instr-variant-content-v10{min-width:0;overflow-wrap:anywhere;}
.detail-source-grid-v10,.detail-rism-record-grid-v10{display:grid;grid-template-columns:minmax(0,82px) minmax(0,1fr);gap:6px 10px;align-items:start;}
.detail-source-k-v10,.detail-rism-record-grid-v10 .k{font-size:.77rem;color:var(--muted);font-weight:680;}
.detail-source-v-v10,.detail-rism-record-grid-v10 .v{font-size:.86rem;color:#1f2937;overflow-wrap:anywhere;display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;font-family:inherit;}
.detail-rism-label-v10{display:inline-flex;align-items:center;border-radius:999px;padding:1px 5px 0;font-size:.55rem;line-height:1.25;letter-spacing:.11em;text-transform:uppercase;font-weight:800;opacity:.68;white-space:nowrap;color:var(--violet-text);background:var(--violet-bg);border:1px solid var(--violet-border);}
.detail-holdings-v10{margin-top:10px;border-top:1px solid #e1e5f5;padding-top:8px;}
.detail-holdings-v10 summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:6px;font-size:.84rem;color:#374151;font-weight:650;}
.detail-holdings-v10 summary::-webkit-details-marker{display:none;}
.detail-arrow-v10{display:inline-flex;width:16px;height:16px;align-items:center;justify-content:center;border-radius:999px;border:1px solid #cfd5ed;color:var(--muted);transition:transform .15s ease;font-size:.95rem;line-height:1;flex:0 0 auto;}
.detail-holdings-v10[open] .detail-arrow-v10,.detail-doc-v10[open] > summary .detail-arrow-v10{transform:rotate(90deg);}
.detail-holdings-list-v10{margin:7px 0 0;padding-left:17px;max-height:180px;overflow:auto;font-size:.80rem;color:#374151;line-height:1.32;}
.detail-doc-v10 summary{list-style:none;padding:9px 12px;color:#374151;font-weight:700;font-size:.86rem;display:flex;align-items:center;justify-content:space-between;gap:8px;cursor:default;}
.detail-doc-v10 summary::-webkit-details-marker{display:none;}
.detail-doc-body-v10{border-top:1px solid #e1e5f5;padding:10px 12px;font-size:.86rem;color:#1f2937;line-height:1.36;overflow-wrap:anywhere;}
.detail-doc-subtitle-v10{font-size:.70rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);font-weight:760;margin:0 0 4px;}
.detail-doc-subtitle-v10:not(:first-child){margin-top:10px;}
.detail-content-section-v10{margin-top:10px;border-top:1px solid #e1e5f5;padding-top:9px;}
.detail-content-list-v10{display:flex;flex-direction:column;gap:7px;}
.detail-content-card-v10{display:grid;grid-template-columns:minmax(58px,72px) minmax(0,1fr) minmax(155px,220px);gap:4px 12px;border:1px solid #e1e5f5;background:#fff;border-radius:14px;padding:8px 10px;align-items:center;}
.detail-content-ref-v10{grid-row:1 / span 3;color:#8a91a0;font-size:.68rem;font-weight:650;letter-spacing:.035em;align-self:start;padding-top:2px;}
.detail-content-title-v10{grid-column:2;font-size:.90rem;font-weight:760;line-height:1.25;color:#111827;overflow-wrap:anywhere;}
.detail-content-composer-v10{grid-column:3;grid-row:1;color:#4b5563;font-size:.80rem;text-align:right;align-self:center;line-height:1.25;}
.detail-content-instr-v10{grid-column:2 / 4;font-size:.80rem;color:#4b5563;line-height:1.32;margin-top:0;overflow-wrap:anywhere;}
.detail-content-link-v10{grid-column:2 / 4;margin-top:1px;font-size:.78rem;color:var(--accent);font-weight:650;}
.detail-conc-block-v10 .conc-heading{padding:9px 12px;margin:0;color:#374151;font-weight:700;font-size:.86rem;text-transform:none;letter-spacing:0;}
.detail-conc-block-v10 .conc-cards{border-top:1px solid #e1e5f5;padding:10px 12px;}
.detail-conc-block-v10 .conc-card{box-shadow:none;}
.index-content-row.subpiece-line{display:grid;grid-template-columns:minmax(48px,58px) minmax(0,1fr) minmax(130px,200px);gap:4px 10px;align-items:center;}
.index-content-row .index-piece-ref{grid-row:1 / span 3;}
.index-content-title{grid-column:2;font-weight:760;}
.index-content-composer{grid-column:3;grid-row:1;color:var(--muted);font-size:.78rem;text-align:right;line-height:1.25;}
.index-content-instr{grid-column:2 / 4;}.index-content-extra{grid-column:2 / 4;}
@media (max-width:760px){.index-content-row.subpiece-line,.detail-content-card-v10{grid-template-columns:minmax(48px,58px) minmax(0,1fr);}.index-content-composer,.detail-content-composer-v10{grid-column:2;grid-row:auto;text-align:left;}.index-content-instr,.index-content-extra,.detail-content-instr-v10,.detail-content-link-v10{grid-column:2;}.index-instr-variant,.detail-instr-variant-v10{grid-template-columns:1fr;gap:2px;}}
@media (min-width:901px){.detail-doc-v10 summary .detail-arrow-v10{display:none;}}
@media (max-width:900px){.detail-columns-v10{grid-template-columns:1fr;}.detail-topline-v10{flex-direction:column;}.detail-tags{justify-content:flex-start;}.detail-doc-v10 summary{cursor:pointer;}}

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

    If both principal and alternative instrumentations exist, use a compact
    Principal / Alternative two-row layout. If only one instrumentation exists,
    do not add an extra Principal label.
    """
    main_html = format_uniform_instr_content(rec.get("instr_rism_main_raw", ""))
    alt_html = format_uniform_instr_content(rec.get("instr_rism_alt_raw", ""))

    if main_html and alt_html:
        return (
            '<div class="index-instr-variants">'
            '<div class="index-instr-variant"><span class="index-instr-variant-label">Principal</span>'
            f'<span class="index-instr-variant-content">{main_html}</span></div>'
            '<div class="index-instr-variant"><span class="index-instr-variant-label">Alternative</span>'
            f'<span class="index-instr-variant-content">{alt_html}</span></div>'
            '</div>'
        )

    if main_html:
        return main_html
    if alt_html:
        return alt_html
    if clean_str(rec.get("instr_catalogs_raw", "")):
        return escape_with_italics(rec.get("instr_catalogs_raw", ""))
    return ""

def parse_rism_publisher_printer_rows(raw):
    """
    Format RISM structured edition relations without normalizing them.

    If every non-empty line has a clear "Role: value" structure, group
    identical roles and use the RISM role as the site label. For example:
      Publisher: A
      Publisher: B
    becomes one Publisher row with two lines.

    If the cell is irregular, fall back to the general label
    "Publisher / printer" and display the content as-is.
    """
    s = clean_str(raw)
    if not s:
        return []

    lines = [ln.strip() for ln in re.split(r"\r?\n+", s) if ln.strip()]
    if not lines:
        return []

    grouped = []
    index = {}

    for line in lines:
        m = re.match(r"^([A-Za-z][A-Za-z /_-]*?)\s*:\s*(.+)$", line)
        if not m:
            return [("Publisher / printer", escape_textnode(s))]

        role_raw = re.sub(r"\s+", " ", m.group(1).strip())
        value = m.group(2).strip()
        if not value:
            return [("Publisher / printer", escape_textnode(s))]

        role_key = role_raw.casefold()
        role_map = {
            "publisher": "Publisher",
            "printer": "Printer",
        }
        label = role_map.get(role_key)
        if not label:
            return [("Publisher / printer", escape_textnode(s))]

        if label not in index:
            index[label] = []
            grouped.append((label, index[label]))
        index[label].append(value)

    return [(label, "<br>".join(escape_textnode(v) for v in values)) for label, values in grouped]

def first_print_record_with_edition_info(records_list, fallback):
    for rr in records_list:
        if not is_print_source_type(rr.get("source_type_raw", "")):
            continue
        if (clean_str(rr.get("rism_date_raw", ""))
            or clean_str(rr.get("rism_publisher_printer_raw", ""))
            or clean_str(rr.get("rism_publication_place_raw", ""))):
            return rr
    return fallback

def source_grid_rows_html(rows):
    if not rows:
        return '<div class="index-source-note">No edition data available.</div>'
    return (
        '<div class="index-source-grid">'
        + ''.join(
            f'<div class="index-source-k">{escape_textnode(label)}</div><div class="index-source-v">{value_html}</div>'
            for label, value_html in rows
            if clean_str(label) and clean_str(value_html)
        )
        + '</div>'
    )

def build_index_source_panel(rec, group_recs=None):
    """
    Right column for open index cards.
    PRINT: Date + RISM publisher/printer relations + place, only when non-empty.
    MANUSCRIPT: Library / Shelfmark / Year.
    No RISM Online link here; RISM remains in the tag row and detail page.
    """
    group_recs = group_recs or [rec]
    family = source_family_for_records(group_recs)

    if family == "print":
        print_rec = first_print_record_with_edition_info(group_recs, rec)
        rows = []

        if clean_str(print_rec.get("rism_date_raw", "")):
            rows.append(("Date", escape_textnode(print_rec.get("rism_date_raw", ""))))

        rows.extend(parse_rism_publisher_printer_rows(print_rec.get("rism_publisher_printer_raw", "")))

        if clean_str(print_rec.get("rism_publication_place_raw", "")):
            rows.append(("Place", escape_textnode(print_rec.get("rism_publication_place_raw", ""))))

        rows_html = source_grid_rows_html(rows)
        return f"""
          <aside class="index-source-panel">
            <div class="index-panel-title">PRINT</div>
            {rows_html}
          </aside>"""

    if family == "manuscript":
        ident_rec = None
        for rr in group_recs:
            if is_manuscript_source_type(rr.get("source_type_raw", "")) and manuscript_identity_raw(rr):
                ident_rec = rr
                break
        ident_rec = ident_rec or rec

        rows = []
        if clean_str(ident_rec.get("library_raw", "")):
            rows.append(("Library", escape_textnode(ident_rec.get("library_raw", ""))))
        if clean_str(ident_rec.get("shelfmark_raw", "")):
            rows.append(("Shelfmark", f'<span class="source-shelfmark">{escape_textnode(ident_rec.get("shelfmark_raw", ""))}</span>'))
        if clean_str(rec.get("rism_date_raw", "")):
            rows.append(("Date", escape_textnode(rec.get("rism_date_raw", ""))))

        rows_html = source_grid_rows_html(rows)
        return f"""
          <aside class="index-source-panel">
            <div class="index-panel-title">MANUSCRIPT</div>
            {rows_html}
          </aside>"""

    source_type = escape_textnode(rec.get("source_type_raw", ""))
    rows_html = source_grid_rows_html([("Type", source_type)] if source_type else [])
    return f"""
          <aside class="index-source-panel">
            <div class="index-panel-title">SOURCE</div>
            {rows_html}
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
  <link rel="stylesheet" href="style.css?v=detail-v25-case-sensitive-instrumentation-2026-07-01">
</head>
<body class="index-page">
@@HEADER@@
<main class="shell">
  <div class="layout">
    <section id="mobileFilterPanel" class="card search-card" aria-label="Search and filters">
      <div class="card-header search-card-header">
        <h2>Search & filters</h2>
        <div class="search-card-actions">
          <button id="clearAllFilters" type="button" class="tag clear-top-btn">
            Clear all filters
          </button>
          <button id="mobileFilterClose" type="button" class="mobile-filter-close" aria-label="Close filters">×</button>
        </div>
      </div>

      <div class="filters">
        <div class="filters-row">

          <div class="primary-search-block">
            <div class="filter-field">
              <label for="searchInput">Search all</label>
              <input id="searchInput" type="text" placeholder="Composer, title, number, library, bibliography…" />
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
                <span>Search by instrument or quantity</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field instr-suggest-wrap">
                <label for="instrInput">Simple search</label>
                <input id="instrInput" type="text" placeholder="Type or select an instrument…" autocomplete="off" />
                <div class="instr-menu" id="instrMenu">
                  <div class="instr-list" id="instrList"></div>
                </div>
              </div>

              <div class="filter-field search-tool-field">
                <label>Search Tool</label>
                <div class="filter-inline search-tool-controls" style="gap:6px;">
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
                <div class="field-hint search-tool-hint">Add rules by instrument and quantity.</div>
              </div>
            </div>
          </details>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Organology</strong>
                <span>Filter by instrument</span>
              </div>
              <div class="section-arrow">›</div>
            </summary>

            <div class="section-body">
              <div class="filter-field">
                <label>Match mode</label>
                <div class="filter-inline filter-mode-row">
                  <select id="organologyMatchMode" aria-label="Organology matching mode">
                    <option value="any">Match any</option>
                    <option value="all">Match all</option>
                  </select>
                </div>
              </div>

              <div class="filter-field" style="position:relative;">
                <label for="organologyInput">Instrument</label>
                <input id="organologyInput" type="text" placeholder="Type or select an instrument…" autocomplete="off" />
                <div class="organology-menu" id="organologyMenu">
                  <div class="organology-list" id="organologyList"></div>
                </div>
                <div id="organologyActive" class="active-filter-chips"></div>
              </div>
            </div>
          </details>

          <details class="filter-section">
            <summary>
              <div class="section-title">
                <strong>Date</strong>
                <span>Filter by source date</span>
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
                <input id="libraryInput" type="text" placeholder="Type or select a siglum: GB-Lbl, A-Wn…" autocomplete="off" />
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
                <span>Search by RISM number</span>
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

    <section class="card catalogue-card">
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
  const mobileFilterToggle = document.getElementById('mobileFilterToggle');
  const mobileFilterClose = document.getElementById('mobileFilterClose');
  const mobileFilterMedia = window.matchMedia('(max-width: 700px)');

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

  const organologyInput = document.getElementById('organologyInput');
  const organologyMenu = document.getElementById('organologyMenu');
  const organologyList = document.getElementById('organologyList');
  const organologyActive = document.getElementById('organologyActive');
  const organologyMatchMode = document.getElementById('organologyMatchMode');

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

  // v25: in instrumentation codes, uppercase/lowercase can have different meanings.
  // A = Alto voice; a = Alto instrument, etc. This affects only instrumentation
  // simple search, not the Organology system.
  const CASE_SENSITIVE_INSTR_CODES = new Set(['S', 's', 'A', 'a', 'T', 't', 'B', 'b']);

  function escapeRegExp(s){
    return String(s || '').replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
  }

  function instrumentCodeTokenRegex(code){
    return new RegExp(
      '(^|[^A-Za-zÀ-ÖØ-öø-ÿ0-9_.:-])' +
      escapeRegExp(code) +
      '($|[^A-Za-zÀ-ÖØ-öø-ÿ0-9_.:-])'
    );
  }

  function matchesSimpleInstrumentQuery(card, queryRaw){
    const q = (queryRaw || '').trim();
    if(!q) return true;

    const raw = card.dataset.instr || '';

    // For single-letter ZinkNET instrumentation codes, case matters.
    if(CASE_SENSITIVE_INSTR_CODES.has(q)){
      return instrumentCodeTokenRegex(q).test(raw);
    }

    return normalize(raw).includes(normalize(q));
  }


  function optionLabel(obj){
    return (obj && (obj.d || obj.k || '')) || '';
  }

  function optionCount(obj){
    const n = Number(obj && obj.n);
    return Number.isFinite(n) ? n : 0;
  }

  function compareBrowseOptions(a, b){
    const an = optionCount(a);
    const bn = optionCount(b);
    if(an !== bn) return bn - an;
    return optionLabel(a).localeCompare(optionLabel(b), undefined, {sensitivity:'base'});
  }

  function browseOptions(options, query, limit, matcher){
    const q = normalizeLoose(query);
    const out = [];
    for(const obj of options || []){
      const ok = q ? matcher(obj, q) : true;
      if(ok) out.push(obj);
    }
    out.sort(compareBrowseOptions);
    return out.slice(0, limit);
  }
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

  // ============ Floating dropdown layering
  function dropdownSectionFor(el){
    return el ? el.closest('details.filter-section') : null;
  }

  function clearDropdownActiveSections(){
    document.querySelectorAll('details.filter-section.dropdown-active').forEach(sec => {
      sec.classList.remove('dropdown-active');
    });
  }

  function activateDropdownSection(el){
    clearDropdownActiveSections();
    const sec = dropdownSectionFor(el);
    if(sec) sec.classList.add('dropdown-active');
  }

  function anyFloatingMenuOpen(){
    return (
      (composerMenu && composerMenu.style.display === 'block') ||
      (instrMenu && instrMenu.style.display === 'block') ||
      (bibMenu && bibMenu.style.display === 'block') ||
      (libraryMenu && libraryMenu.style.display === 'block') ||
      (organologyMenu && organologyMenu.style.display === 'block')
    );
  }

  function clearDropdownActiveIfNoneOpen(){
    if(!anyFloatingMenuOpen()) clearDropdownActiveSections();
  }

  // ============ Desktop app-layout measurements + fixed floating menus
  const appHeader = document.querySelector('header.app-header');
  const appFilters = document.querySelector('.search-card .filters');
  const appLayoutMedia = window.matchMedia('(min-width: 1100px)');

  function updateIndexAppMetrics(){
    if(!document.body.classList.contains('index-page')) return;
    const h = appHeader ? Math.ceil(appHeader.getBoundingClientRect().height) : 104;
    document.documentElement.style.setProperty('--index-header-height', `${h}px`);
  }

  function setMobileFilterPanel(open){
    if(!document.body.classList.contains('index-page')) return;

    const shouldOpen = !!open && mobileFilterMedia.matches;
    document.body.classList.toggle('filters-open', shouldOpen);

    if(mobileFilterToggle){
      mobileFilterToggle.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
      mobileFilterToggle.setAttribute('aria-label', shouldOpen ? 'Close filters' : 'Open filters');
    }

    if(!shouldOpen){
      closeAllFloatingMenus();
    } else {
      updateIndexAppMetrics();
    }
  }

  function toggleMobileFilterPanel(){
    setMobileFilterPanel(!document.body.classList.contains('filters-open'));
  }

  function useFixedMenus(){
    return document.body.classList.contains('index-page') && appLayoutMedia.matches;
  }

  function clearFixedMenu(menuEl){
    if(!menuEl) return;
    menuEl.classList.remove('is-fixed-menu');
    menuEl.style.left = '';
    menuEl.style.top = '';
    menuEl.style.width = '';
    menuEl.style.maxHeight = '';
  }

  function resetAllFixedMenus(){
    [composerList, instrList, bibMenu, libraryList, organologyList].forEach(clearFixedMenu);
  }

  function placeFixedMenu(menuEl, anchorEl, opts={}){
    if(!menuEl || !anchorEl) return;
    if(!useFixedMenus()){
      clearFixedMenu(menuEl);
      return;
    }

    const margin = 12;
    const rect = anchorEl.getBoundingClientRect();
    const headerBottom = appHeader ? appHeader.getBoundingClientRect().bottom : 0;
    const offsetY = opts.offsetY ?? 5;
    const naturalMaxHeight = opts.maxHeight ?? (opts.wide ? 360 : 260);

    let top = Math.max(rect.bottom + offsetY, headerBottom + 6);
    let availableHeight = window.innerHeight - top - margin;
    if(availableHeight < 140){
      top = headerBottom + 6;
      availableHeight = window.innerHeight - top - margin;
    }
    const maxHeight = Math.max(140, Math.min(naturalMaxHeight, availableHeight));

    let width;
    if(opts.wide){
      width = Math.min(760, window.innerWidth - margin * 2);
    } else {
      const minWidth = opts.minWidth ?? 180;
      width = Math.min(Math.max(rect.width, minWidth), window.innerWidth - margin * 2);
    }

    let left = rect.left;
    if(left + width > window.innerWidth - margin) left = window.innerWidth - margin - width;
    if(left < margin) left = margin;

    menuEl.classList.add('is-fixed-menu');
    menuEl.style.left = `${Math.round(left)}px`;
    menuEl.style.top = `${Math.round(top)}px`;
    menuEl.style.width = `${Math.round(width)}px`;
    menuEl.style.maxHeight = `${Math.round(maxHeight)}px`;
  }

  function placeOpenFixedMenus(){
    updateIndexAppMetrics();
    if(composerMenu && composerMenu.style.display === 'block'){
      placeFixedMenu(composerList, composerInput, {maxHeight:240});
    }
    if(instrMenu && instrMenu.style.display === 'block'){
      placeFixedMenu(instrList, instrInput, {maxHeight:280});
    }
    if(bibMenu && bibMenu.style.display === 'block'){
      placeFixedMenu(bibMenu, bibToggle, {wide:true, maxHeight:360});
    }
    if(libraryMenu && libraryMenu.style.display === 'block'){
      placeFixedMenu(libraryList, libraryInput, {maxHeight:260});
    }
    if(organologyMenu && organologyMenu.style.display === 'block'){
      placeFixedMenu(organologyList, organologyInput, {maxHeight:260});
    }
  }

  updateIndexAppMetrics();
  window.addEventListener('resize', placeOpenFixedMenus);
  window.addEventListener('scroll', placeOpenFixedMenus, {passive:true});
  if(appFilters){
    appFilters.addEventListener('scroll', placeOpenFixedMenus, {passive:true});
  }
  if(appLayoutMedia.addEventListener){
    appLayoutMedia.addEventListener('change', placeOpenFixedMenus);
  }

  if(mobileFilterToggle){
    mobileFilterToggle.addEventListener('click', toggleMobileFilterPanel);
  }
  if(mobileFilterClose){
    mobileFilterClose.addEventListener('click', () => setMobileFilterPanel(false));
  }
  if(mobileFilterMedia.addEventListener){
    mobileFilterMedia.addEventListener('change', (ev) => {
      if(!ev.matches) setMobileFilterPanel(false);
      updateIndexAppMetrics();
    });
  }

  function closeAllFloatingMenus(except){
    if(except !== 'composer'){
      composerMenu.style.display = 'none';
      composerList.innerHTML = '';
    }
    if(except !== 'instr' && instrMenu){
      instrMenu.style.display = 'none';
      instrList.innerHTML = '';
    }
    if(except !== 'bib'){
      bibMenu.style.display = 'none';
    }
    if(except !== 'library'){
      libraryMenu.style.display = 'none';
      libraryList.innerHTML = '';
    }
    if(except !== 'organology' && organologyMenu){
      organologyMenu.style.display = 'none';
      organologyList.innerHTML = '';
    }
    resetAllFixedMenus();
    clearDropdownActiveSections();
  }

  // ============ Composer dropdown
  const WORD_RE = /[A-Za-zÀ-ÖØ-öø-ÿ]+/g;
  function wordsOnly(s){ return (normalize(s).match(WORD_RE) || []); }

  const COMPOSERS = @@COMPOSERS@@;

  let composerSelected = "";

  function closeComposerMenu(){
    composerMenu.style.display = 'none';
    composerList.innerHTML = '';
    clearFixedMenu(composerList);
    clearDropdownActiveIfNoneOpen();
  }

  function openComposerMenu(items){
    closeAllFloatingMenus('composer');
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
    if(items.length){
      activateDropdownSection(composerMenu);
      placeFixedMenu(composerList, composerInput, {maxHeight:240});
    } else {
      clearFixedMenu(composerList);
      clearDropdownActiveIfNoneOpen();
    }
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
  const SEARCH_TOOL_DISPLAY = new Map(SEARCH_TOOL_INSTRS.map(o => [o.k, o.d || o.k]));
  const stRules = [];

  function searchToolDisplay(k){
    return SEARCH_TOOL_DISPLAY.get(k) || k;
  }

  SEARCH_TOOL_INSTRS.forEach(o => {
    const opt = document.createElement('option');
    opt.value = o.k;
    opt.textContent = `${o.d || o.k} (${o.n})`;
    opt.title = o.k;
    stInstr.appendChild(opt);
  });

  function closeInstrMenu(){
    if(!instrMenu) return;
    instrMenu.style.display = 'none';
    instrList.innerHTML = '';
    clearFixedMenu(instrList);
    clearDropdownActiveIfNoneOpen();
  }

  function computeInstrHits(){
    return browseOptions(
      SEARCH_TOOL_INSTRS,
      instrInput.value,
      60,
      (obj, q) => normalizeLoose(obj.k).includes(q) || normalizeLoose(obj.d || "").includes(q)
    );
  }

  function openInstrMenu(items){
    if(!instrMenu) return;
    closeAllFloatingMenus('instr');
    instrList.innerHTML = '';
    items.forEach(obj => {
      const div = document.createElement('div');
      div.className = 'instr-item';
      if(normalizeLoose(instrInput.value) === normalizeLoose(obj.k)) div.classList.add('is-selected');

      const name = document.createElement('span');
      name.className = 'choice-item-label';
      name.textContent = obj.d || obj.k;

      const count = document.createElement('span');
      count.className = 'instr-item-count';
      count.textContent = obj.n;

      div.appendChild(name);
      div.appendChild(count);
      div.addEventListener('click', () => {
        instrInput.value = obj.k;
        closeInstrMenu();
        applyFilters();
      });
      instrList.appendChild(div);
    });
    instrMenu.style.display = items.length ? 'block' : 'none';
    if(items.length){
      activateDropdownSection(instrMenu);
      placeFixedMenu(instrList, instrInput, {maxHeight:280});
    } else {
      clearFixedMenu(instrList);
      clearDropdownActiveIfNoneOpen();
    }
  }

  function renderStRules(){
    stActive.innerHTML = '';
    stRules.forEach((r, idx) => {
      const chip = document.createElement('span');
      chip.className = 'tag tag-conc';
      chip.style.cursor = 'pointer';
      const sign = r.mode === 'include' ? '+' : '–';
      const cmp = (r.cmp === 'eq') ? '=' : '≥';
      chip.textContent = `${sign} ${searchToolDisplay(r.k)} ${cmp} ${r.n} ×`;
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
    clearFixedMenu(bibMenu);
    clearDropdownActiveIfNoneOpen();
  }

  function openBibMenu(){
    closeAllFloatingMenus('bib');
    bibMenu.style.display = 'block';
    activateDropdownSection(bibMenu);
    placeFixedMenu(bibMenu, bibToggle, {wide:true, maxHeight:360});
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
    clearFixedMenu(libraryList);
    clearDropdownActiveIfNoneOpen();
  }

  function openLibraryMenu(items){
    closeAllFloatingMenus('library');
    libraryList.innerHTML = '';
    items.forEach(obj => {
      const div = document.createElement('div');
      div.className = 'library-item';
      if(selectedLibraries.includes(obj.k)) div.classList.add('is-selected');
      div.title = obj.d;

      const label = document.createElement('span');
      label.className = 'choice-item-label';
      label.textContent = obj.d;

      const count = document.createElement('span');
      count.className = 'choice-item-count';
      count.textContent = obj.n ? obj.n : '';

      div.appendChild(label);
      div.appendChild(count);
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
    if(items.length){
      activateDropdownSection(libraryMenu);
      placeFixedMenu(libraryList, libraryInput, {maxHeight:260});
    } else {
      clearFixedMenu(libraryList);
      clearDropdownActiveIfNoneOpen();
    }
  }

  function computeLibraryHits(){
    return browseOptions(
      LIBRARY_OPTIONS,
      libraryInput.value,
      80,
      (obj, q) => normalizeLoose(obj.d).includes(q) || normalizeLoose(obj.k).includes(q)
    );
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

  // ============ Organology dedicated multi-select filter
  const ORGANOLOGY_OPTIONS = @@ORGANOLOGY_OPTIONS@@;
  const ORGANOLOGY_DISPLAY = new Map(ORGANOLOGY_OPTIONS.map(o => [o.k, o.d]));
  const selectedOrganology = [];

  function normalizeOrganologyCode(s){
    return normalizeLoose(s);
  }

  function closeOrganologyMenu(){
    if(!organologyMenu) return;
    organologyMenu.style.display = 'none';
    organologyList.innerHTML = '';
    clearFixedMenu(organologyList);
    clearDropdownActiveIfNoneOpen();
  }

  function openOrganologyMenu(items){
    if(!organologyMenu) return;
    closeAllFloatingMenus('organology');
    organologyList.innerHTML = '';
    items.forEach(obj => {
      const div = document.createElement('div');
      div.className = 'organology-item';
      if(selectedOrganology.includes(obj.k)) div.classList.add('is-selected');
      div.title = obj.d;

      const label = document.createElement('span');
      label.className = 'choice-item-label';
      label.textContent = obj.d;

      const count = document.createElement('span');
      count.className = 'choice-item-count';
      count.textContent = obj.n ? obj.n : '';

      div.appendChild(label);
      div.appendChild(count);
      div.addEventListener('click', () => {
        if(!selectedOrganology.includes(obj.k)){
          selectedOrganology.push(obj.k);
        }
        organologyInput.value = '';
        closeOrganologyMenu();
        renderOrganologyChips();
        updateOrgFilterBadge();
        applyFilters();
      });
      organologyList.appendChild(div);
    });
    organologyMenu.style.display = items.length ? 'block' : 'none';
    if(items.length){
      activateDropdownSection(organologyMenu);
      placeFixedMenu(organologyList, organologyInput, {maxHeight:260});
    } else {
      clearFixedMenu(organologyList);
      clearDropdownActiveIfNoneOpen();
    }
  }

  function computeOrganologyHits(){
    return browseOptions(
      ORGANOLOGY_OPTIONS,
      organologyInput.value,
      80,
      (obj, q) => normalizeOrganologyCode(obj.d).includes(q) || normalizeOrganologyCode(obj.k).includes(q)
    );
  }

  function renderOrganologyChips(){
    organologyActive.innerHTML = '';
    selectedOrganology.forEach(k => {
      const display = ORGANOLOGY_DISPLAY.get(k) || k;
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
        const idx = selectedOrganology.indexOf(k);
        if(idx >= 0) selectedOrganology.splice(idx, 1);
        renderOrganologyChips();
        updateOrgFilterBadge();
        applyFilters();
      });
      organologyActive.appendChild(chip);
    });
  }

  function setOrganologySelection(keys){
    selectedOrganology.length = 0;
    (keys || []).forEach(k => {
      const key = normalizeOrganologyCode(k);
      if(key && !selectedOrganology.includes(key)) selectedOrganology.push(key);
    });
    renderOrganologyChips();
  }

  organologyInput.addEventListener('input', () => {
    const hits = computeOrganologyHits();
    if(!hits.length) closeOrganologyMenu();
    else openOrganologyMenu(hits);
  });

  organologyInput.addEventListener('focus', () => {
    const hits = computeOrganologyHits();
    if(hits.length) openOrganologyMenu(hits);
  });

  organologyMatchMode.addEventListener('change', applyFilters);

  // ============ Organology link filter
  // Supported URL fragments:
  //   index.html#org=IDENTIFIER
  //   index.html#organology=IDENTIFIER
  //   index.html#org=cnto,trb
  //   index.html#org=cnto;trb
  //
  // This now activates the dedicated Organology filter instead of filling
  // the global Search all field.
  const orgFilterBadge = document.createElement('div');
  orgFilterBadge.id = 'orgFilterBadge';
  orgFilterBadge.style.display = 'none';
  orgFilterBadge.style.margin = '0 0 10px';
  orgFilterBadge.style.fontSize = '0.86rem';
  orgFilterBadge.style.color = 'var(--violet-text)';
  orgFilterBadge.style.fontWeight = '600';
  orgFilterBadge.style.cursor = 'pointer';

  entriesContainer.insertAdjacentElement('beforebegin', orgFilterBadge);

  function parseOrganologyHashCodes(value){
    const raw = value || '';
    return raw
      .split(/[;,]+/)
      .map(v => normalizeOrganologyCode(v))
      .filter(Boolean);
  }

  function readOrgFilterFromHash() {
    const raw = (window.location.hash || '').replace(/^#/, '');
    if (!raw) return [];

    const params = new URLSearchParams(raw);
    const value = params.get('org') || params.get('organology') || '';
    return parseOrganologyHashCodes(value);
  }

  function clearOrgHash() {
    if (window.location.hash) {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  function updateOrgFilterBadge(){
    if (!selectedOrganology.length) {
      orgFilterBadge.style.display = 'none';
      orgFilterBadge.textContent = '';
      return;
    }

    const labels = selectedOrganology.map(k => ORGANOLOGY_DISPLAY.get(k) || k);
    orgFilterBadge.style.display = '';
    orgFilterBadge.innerHTML = `Organology filter: <strong>${labels.join(', ')}</strong> ×`;
    orgFilterBadge.title = 'Click to clear this Organology filter';
  }

  function applyOrgFilterFromHash() {
    const keys = readOrgFilterFromHash();
    if (!keys.length) {
      updateOrgFilterBadge();
      return;
    }
    setOrganologySelection(keys);
    updateOrgFilterBadge();
  }

  orgFilterBadge.addEventListener('click', () => {
    clearOrgHash();
    setOrganologySelection([]);
    updateOrgFilterBadge();
    applyFilters();
  });

  window.addEventListener('hashchange', () => {
    applyOrgFilterFromHash();
    applyFilters();
  });

  renderOrganologyChips();
  applyOrgFilterFromHash();

  // ============ Clear all filters
  function clearAllFiltersFn() {
    searchInput.value = '';

    composerInput.value = '';
    composerSelected = '';
    closeComposerMenu();

    instrInput.value = '';
    closeInstrMenu();
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

    setOrganologySelection([]);
    organologyMatchMode.value = 'any';
    organologyInput.value = '';
    closeOrganologyMenu();
    updateOrgFilterBadge();

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

  function parseOrganologyPieces(card){
    return parseJsonDataset(card, 'organologyPieces', '__organologyPieces');
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

  // ============ Matching logic: Organology
  function matchesOrganologyFilter(card){
    if(!selectedOrganology.length) return {ok:true, matchPids:new Set()};

    const mode = organologyMatchMode.value || 'any';
    const pieces = parseOrganologyPieces(card);
    if(!pieces.length) return {ok:false, matchPids:new Set()};

    const matchPids = new Set();
    for(const p of pieces){
      const values = p.values || [];
      if(intersectsOrContains(values, selectedOrganology, mode)){
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
    const qiRaw = (instrInput.value || '').trim();
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
    const organologyActiveOn = selectedOrganology.length > 0;
    const rismActiveOn = !!normalizeRismNo(rismNoInput.value);

    const pieceLevelActive =
      stActiveOn ||
      yrActiveOn ||
      compActiveOn ||
      bibActiveOn ||
      libraryActiveOn ||
      organologyActiveOn ||
      rismActiveOn;

    cards.forEach(card => {
      const text  = normalize(card.dataset.search);
      const mts = (card.dataset.musicTypes || '').split('||').filter(Boolean);
      const sourceCats = (card.dataset.sourceCategories || '').split('||').filter(Boolean);
      const msDetails = (card.dataset.msDetails || '').split('||').filter(Boolean);

      let ok = true;
      if (q  && !text.includes(q)) ok = false;
      if (qiRaw && !matchesSimpleInstrumentQuery(card, qiRaw)) ok = false;
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

      let organologyMatch = {ok:true, matchPids:new Set()};
      if(ok){
        organologyMatch = matchesOrganologyFilter(card);
        if(!organologyMatch.ok) ok = false;
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
        if(organologyActiveOn) sets.push(organologyMatch.matchPids);
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
  instrInput.addEventListener('input', () => {
    applyFilters();
    const hits = computeInstrHits();
    if(!hits.length) closeInstrMenu();
    else openInstrMenu(hits);
  });
  instrInput.addEventListener('focus', () => {
    const hits = computeInstrHits();
    if(hits.length) openInstrMenu(hits);
  });
  yearFrom.addEventListener('input', applyFilters);
  yearTo.addEventListener('input', applyFilters);
  musicFilter.addEventListener('change', applyFilters);
  sourceFilter.addEventListener('change', () => {
    updateMsDetailVisibility();
    applyFilters();
  });
  msDetailFilter.addEventListener('change', applyFilters);
  rismNoInput.addEventListener('input', applyFilters);

  document.addEventListener('keydown', (ev) => {
    if(ev.key === 'Escape'){
      if(document.body.classList.contains('filters-open')){
        setMobileFilterPanel(false);
      } else {
        closeAllFloatingMenus();
      }
    }
  });

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
    if(organologyMenu && !organologyMenu.contains(ev.target) && ev.target !== organologyInput){
      closeOrganologyMenu();
    }
    if(!bibMenu.contains(ev.target) && ev.target !== bibToggle){
      closeBibMenu();
    }
    clearDropdownActiveIfNoneOpen();
  });

  applySort();
  applyFilters();
</script>
</body>
</html>
"""


def detail_rism_label():
    return '<span class="detail-rism-label-v10">RISM</span>'

def detail_source_row(label, value_html, rism=False):
    if not clean_str(value_html):
        return ""
    badge = detail_rism_label() if rism else ""
    return f'<div class="detail-source-k-v10">{escape_textnode(label)}</div><div class="detail-source-v-v10"><span>{value_html}</span>{badge}</div>'

def detail_holdings_html(raw):
    lines = holdings_lines(raw)
    if not lines:
        return ""
    lis = "".join(f"<li>{html.escape(ln, quote=False)}</li>" for ln in lines)
    return f'''
          <details class="detail-holdings-v10">
            <summary><span class="detail-arrow-v10">›</span><span>Holdings ({len(lines)})</span>{detail_rism_label()}</summary>
            <ul class="detail-holdings-list-v10">{lis}</ul>
          </details>'''

def detail_source_panel_html(rec):
    if is_print_source_type(rec.get("source_type_raw", "")):
        rows = []
        if clean_str(rec.get("rism_date_raw", "")):
            rows.append(detail_source_row("Date", escape_textnode(rec.get("rism_date_raw", "")), rism=True))
        for label, value_html in parse_rism_publisher_printer_rows(rec.get("rism_publisher_printer_raw", "")):
            rows.append(detail_source_row(label, value_html, rism=True))
        if clean_str(rec.get("rism_publication_place_raw", "")):
            rows.append(detail_source_row("Place", escape_textnode(rec.get("rism_publication_place_raw", "")), rism=True))
        rows_html = "".join(rows) or '<div class="index-source-note">No edition data available.</div>'
        return f'''
        <aside class="detail-panel-v10">
          <div class="detail-panel-title-v10">PRINT</div>
          <div class="detail-source-grid-v10">{rows_html}</div>
          {detail_holdings_html(rec.get("rism_holdings_raw", ""))}
        </aside>'''

    if is_manuscript_source_type(rec.get("source_type_raw", "")) or clean_str(rec.get("library_raw", "")) or clean_str(rec.get("shelfmark_raw", "")):
        rows = []
        if clean_str(rec.get("library_raw", "")):
            rows.append(detail_source_row("Library", escape_textnode(rec.get("library_raw", "")), rism=False))
        if clean_str(rec.get("shelfmark_raw", "")):
            rows.append(detail_source_row("Shelfmark", f'<span class="source-shelfmark">{escape_textnode(rec.get("shelfmark_raw", ""))}</span>', rism=False))
        if clean_str(rec.get("rism_date_raw", "")):
            rows.append(detail_source_row("Date", escape_textnode(rec.get("rism_date_raw", "")), rism=True))
        rows_html = "".join(rows) or '<div class="index-source-note">No source data available.</div>'
        return f'''
        <aside class="detail-panel-v10">
          <div class="detail-panel-title-v10">MANUSCRIPT</div>
          <div class="detail-source-grid-v10">{rows_html}</div>
          {detail_holdings_html(rec.get("rism_holdings_raw", ""))}
        </aside>'''

    if clean_str(rec.get("source_type_raw", "")):
        return f'''
        <aside class="detail-panel-v10">
          <div class="detail-panel-title-v10">SOURCE</div>
          <div class="detail-source-grid-v10">{detail_source_row("Type", escape_textnode(rec.get("source_type_raw", "")), rism=False)}</div>
        </aside>'''
    return ""

def detail_rism_record_html(rec):
    rno = clean_numberish(rec.get("rism_no_raw", ""))
    link = norm_url(rec.get("rism_link_raw", ""))
    if not rno and not link:
        return ""
    rows = []
    if rno:
        rows.append(f'<div class="k">RISM No.</div><div class="v">{escape_textnode(rno)}</div>')
    if link:
        rows.append(f'<div class="k">Link</div><div class="v"><a href="{escape_attr(link)}" target="_blank" rel="noopener">View in RISM Online</a></div>')
    return f'''
        <details class="detail-doc-v10" open>
          <summary><span>RISM record</span><span class="detail-arrow-v10">›</span></summary>
          <div class="detail-doc-body-v10"><div class="detail-rism-record-grid-v10">{"".join(rows)}</div></div>
        </details>'''

def detail_doc_section_html(title, body_html, full_span=False):
    if not clean_str(body_html):
        return ""
    full = " full-span" if full_span else ""
    return f'''
        <details class="detail-doc-v10{full}" open>
          <summary><span>{escape_textnode(title)}</span><span class="detail-arrow-v10">›</span></summary>
          <div class="detail-doc-body-v10">{body_html}</div>
        </details>'''

def detail_catalogue_bibliography_html(rec):
    if rec.get("indiv_coll") == "VirtualColl":
        return ""
    bits = []
    if clean_str(rec.get("instr_catalogs_raw", "")):
        bits.append(f'<div class="detail-doc-subtitle-v10">Instrumentation from catalogues</div><div>{escape_with_italics(rec.get("instr_catalogs_raw", ""))}</div>')
    if clean_str(rec.get("bibliography_raw", "")):
        bits.append(f'<div class="detail-doc-subtitle-v10">Bibliography</div><div>{rec.get("bibliography", "")}</div>')
    return detail_doc_section_html("Catalogue / Bibliography", "".join(bits), full_span=True)

def detail_note_html(rec):
    if rec.get("indiv_coll") == "VirtualColl" or not clean_str(rec.get("note_raw", "")):
        return ""
    return detail_doc_section_html("Notes", rec.get("note", ""), full_span=False)

def detail_organology_html(rec):
    if rec.get("indiv_coll") == "VirtualColl" or not clean_str(rec.get("organology_raw", "")):
        return ""
    return detail_doc_section_html("Organology", rec.get("organology", ""), full_span=False)

def detail_is_collection_record(rec):
    return rec.get("indiv_coll") == "VirtualColl" or is_real_collection_record(rec)

def detail_instr_html(rec):
    # Collection pages should go directly from COLLECTION/title to Content.
    # Do not fill the main Instrumentation block from Instrumentation from Catalogs.
    if detail_is_collection_record(rec):
        return ""

    main_html = format_uniform_instr_content(rec.get("instr_rism_main_raw", ""))
    alt_html = format_uniform_instr_content(rec.get("instr_rism_alt_raw", ""))

    if main_html and alt_html:
        body = f'''
            <div class="detail-instr-variants-v10">
              <div class="detail-instr-variant-v10">
                <div class="detail-instr-variant-label-v10">Principal</div>
                <div class="detail-instr-variant-content-v10">{main_html}</div>
              </div>
              <div class="detail-instr-variant-v10">
                <div class="detail-instr-variant-label-v10">Alternative</div>
                <div class="detail-instr-variant-content-v10">{alt_html}</div>
              </div>
            </div>'''
    else:
        single_html = main_html or alt_html
        if not single_html and clean_str(rec.get("instr_catalogs_raw", "")):
            single_html = escape_with_italics(rec.get("instr_catalogs_raw", ""))
        if not single_html:
            return ""
        body = f'<div>{single_html}</div>'

    return f'''
          <div class="detail-instr-v10">
            <span class="detail-instr-label-v10">Instrumentation</span>
            {body}
          </div>'''

def detail_content_html(ids_in_group, coll_id, records):
    items = []
    for pid in ids_in_group:
        if coll_id and pid == coll_id:
            continue
        pr = records.get(pid)
        if not pr:
            continue
        title = abbreviated_title_html(pr.get("title_raw", "") or "(Untitled)", max_len=92)
        composer = pr.get("composer") or "Anonymous"
        instr = index_instrumentation_html(pr) or '<span class="muted-value">—</span>'
        items.append(f'''
              <div class="detail-content-card-v10">
                <div class="detail-content-ref-v10">{escape_textnode(pid)}</div>
                <div class="detail-content-title-v10">{title}</div>
                <div class="detail-content-composer-v10">{composer}</div>
                <div class="detail-content-instr-v10">{instr}</div>
                <div class="detail-content-link-v10"><a href="piece-{pid.replace('/','-')}.html" target="_blank" rel="noopener">Open single-work page</a></div>
              </div>''')
    if not items:
        return ""
    return f'''
          <section class="detail-content-section-v10">
            <div class="detail-content-title-label-v10">Content</div>
            <div class="detail-content-list-v10">{"".join(items)}</div>
          </section>'''

def detail_concordances_html(rec, records, used_links_page):
    if rec.get("indiv_coll") == "VirtualColl" or not rec.get("concordances_ids"):
        return ""
    cards_html = []
    for cid in rec.get("concordances_ids", []):
        cr = records.get(cid)
        if not cr:
            continue
        mt = cr.get("music_type_raw", "")
        stt = cr.get("source_type_raw", "")
        mt_tag = f'<span class="tag tag-type">{escape_textnode(mt)}</span>' if mt else ""
        st_tag = f'<span class="tag tag-source">{escape_textnode(stt)}</span>' if stt else ""
        rchip = rism_chip_self(cr, used_links_page)
        cards_html.append(f'''
            <div class="conc-card">
              <a class="conc-id-link" href="piece-{cid.replace('/','-')}.html" target="_blank" rel="noopener">{escape_textnode(cid)}</a>
              <div class="conc-main">
                <div class="conc-title">{cr.get("title") or "(Untitled)"}</div>
                <div class="conc-composer">{cr.get("composer") or ""}</div>
                <div class="conc-tags">{mt_tag}{st_tag}{rchip}</div>
              </div>
            </div>''')
    if not cards_html:
        return ""
    return f'''
        <details class="detail-doc-v10 detail-conc-block-v10 full-span" open>
          <summary><span>Linked concordances</span><span class="detail-arrow-v10">›</span></summary>
          <div class="conc-cards">{"".join(cards_html)}</div>
        </details>'''

def detail_work_or_collection_panel_html(rec, ids_in_group, coll_id, is_virtual_group, records):
    is_collection = detail_is_collection_record(rec)
    panel_title = "COLLECTION" if is_collection else "WORK"
    identity_html = ""
    if clean_str(rec.get("composer_raw", "")):
        identity_html = f'''
          <div class="detail-identity-v10">
            <div class="detail-identity-label-v10">Composer</div>
            <div class="detail-identity-value-v10">{rec.get("composer")}</div>
          </div>
          <div class="detail-soft-rule-v10"></div>'''
    else:
        ident = manuscript_identity_raw(rec)
        if not ident and is_collection:
            child_recs = [records[z] for z in ids_in_group if z in records]
            ident = first_manuscript_identity_raw(child_recs)
        if ident:
            identity_html = f'''
          <div class="detail-identity-v10">
            <div class="detail-identity-label-v10">Source</div>
            <div class="detail-identity-value-v10 source-identity">{escape_textnode(ident)}</div>
          </div>
          <div class="detail-soft-rule-v10"></div>'''
    title = rec.get("title") or "<em>(Untitled)</em>"
    instr = detail_instr_html(rec)
    content = detail_content_html(ids_in_group, coll_id, records) if is_collection else ""
    return f'''
        <section class="detail-panel-v10 detail-main-panel-v10">
          <div class="detail-panel-title-v10">{panel_title}</div>
          {identity_html}
          <div class="detail-title-full-v10">{title}</div>
          {instr}
          {content}
        </section>'''

detail_template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>@@TITLE_FULL@@</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="style.css?v=detail-v25-case-sensitive-instrumentation-2026-07-01">
</head>
<body>
@@HEADER@@
<main class="detail-shell-v10">
  <div class="breadcrumbs"><a href="index.html">ZinkNET index</a>@@BREADCRUMB@@</div>
  @@PARENT_BTN@@
  <article class="detail-page-v10">
    <div class="detail-topline-v10">
      <div class="detail-ref-v10">@@ID@@</div>
      <div class="detail-tags">@@TAGS@@</div>
    </div>
    <div class="detail-columns-v10">
      <div class="detail-left-stack-v10">
        @@MAIN_PANEL@@
        <div class="detail-lower-left-v10">
          @@CATALOGUE_BIBLIOGRAPHY@@
          @@CONC@@
        </div>
      </div>
      <div class="detail-right-stack-v10">
        @@SOURCE_PANEL@@
        @@RISM_RECORD@@
        @@ORG@@
        @@NOTE@@
      </div>
    </div>
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
            "rism_publisher_printer_raw": clean_str(get_col(row, COL_RISM_PUBLISHER_PRINTER)) if (COL_RISM_PUBLISHER_PRINTER in df.columns) else "",
            "rism_publication_place_raw": clean_str(get_col(row, COL_RISM_PUBLICATION_PLACE)) if (COL_RISM_PUBLICATION_PLACE in df.columns) else "",
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
        # Organology is a separate system, not the instrumentation code system.
        # v25: do not apply instrumentation-code labels/tooltips here.
        rec["organology"] = escape_textnode(rec["organology_raw"])

        rec["search_scenarios"] = parse_search_tool_to_scenarios(rec["search_tool_raw"], limit=256)
        rec["search_tool_terms_raw"] = instrument_search_terms_from_scenarios(rec["search_scenarios"])
        rec["year_min"] = parse_int_safe(rec["rism_earliest_year_raw"])
        rec["year_max"] = parse_int_safe(rec["rism_latest_year_raw"])
        rec["bibliography_refs"] = bibliography_refs(rec["bibliography_raw"])
        rec["organology_codes_raw"] = organology_codes(rec["organology_raw"])
        rec["organology_codes_keys"] = [code.casefold() for code in rec["organology_codes_raw"]]
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
        has_real_coll = any(is_real_collection_record(records[z]) for z in ids if z in records)
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
                "search_tool_raw": "", "search_scenarios": [], "search_tool_terms_raw": "",
                "rism_holdings_raw": "", "rism_date_raw": "",
                "rism_earliest_year_raw": "", "rism_latest_year_raw": "",
                "rism_publisher_printer_raw": "", "rism_publication_place_raw": "",
                "year_min": None, "year_max": None,
                "bibliography_refs": [],
                "organology_codes_raw": [],
                "organology_codes_keys": [],
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
        [
            {"k": k, "d": instrument_search_display(k), "n": int(instr_freq.get(k, 0))}
            for k in all_instr_sorted
        ],
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
    # v23 also stores a simple frequency count, used for browseable dropdowns.
    library_display_by_key = {}
    library_count_by_key = {}
    for rec in records.values():
        raw_by_key = {raw.casefold(): raw for raw in rec.get("holdings_library_sigla_raw", [])}
        for key in set(rec.get("holdings_library_sigla_keys", [])):
            display = raw_by_key.get(key, key)
            library_display_by_key.setdefault(key, display)
            library_count_by_key[key] = library_count_by_key.get(key, 0) + 1

    library_options = [
        {"k": k, "d": d, "n": int(library_count_by_key.get(k, 0))}
        for k, d in sorted(
            library_display_by_key.items(),
            key=lambda kv: (-library_count_by_key.get(kv[0], 0), kv[1].casefold())
        )
    ]
    library_options_js = json.dumps(library_options, ensure_ascii=False)

    # Organology instrument-code options
    # Dedupe case-insensitively while preserving a preferred display form.
    # v23 also stores a simple frequency count, used for browseable dropdowns.
    organology_display_by_key = {}
    organology_count_by_key = {}
    for rec in records.values():
        raw_by_key = {raw.casefold(): raw for raw in rec.get("organology_codes_raw", [])}
        for key in set(rec.get("organology_codes_keys", [])):
            raw_display = raw_by_key.get(key, key)
            display = instrument_search_display(raw_display)
            organology_display_by_key.setdefault(key, display)
            organology_count_by_key[key] = organology_count_by_key.get(key, 0) + 1

    organology_options = [
        {"k": k, "d": d, "n": int(organology_count_by_key.get(k, 0))}
        for k, d in sorted(
            organology_display_by_key.items(),
            key=lambda kv: (-organology_count_by_key.get(kv[0], 0), kv[1].casefold())
        )
    ]
    organology_options_js = json.dumps(organology_options, ensure_ascii=False)

    # =========================
    # INDEX BUILD
    # =========================
    group_html_parts = []
    sorted_group_ids = sorted(groups.keys(), key=lambda g: parse_zinknet(g))

    for default_order_idx, gid in enumerate(sorted_group_ids):
        ids = groups[gid]
        coll_id = next((z for z in ids if z in records and is_real_collection_record(records[z])), None)
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
        primary_is_source_identity = bool(
            primary_label_raw
            and not clean_str(hrec.get("composer_raw", ""))
            and source_family_for_records(group_recs) == "manuscript"
        )
        primary_class = "index-source-identity" if primary_is_source_identity else "entry-composer-main"
        primary_style = (
            "font-size:.94rem; font-weight:600; color:var(--muted); "
            "letter-spacing:.01em; line-height:1.18; min-width:0;"
            if primary_is_source_identity else
            "font-size:1.05rem; font-weight:750; color:#020617; line-height:1.15; min-width:0;"
        )
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
                <div class="index-content-title">{content_title}</div>
                <div class="index-content-composer">{content_composer}</div>
                <div class="index-content-instr">{content_instr}</div>
                {('<div class="index-content-extra">' + ''.join(extras) + '</div>') if extras else ''}
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
            if clean_str(title_raw_header):
                title_html = abbreviated_title_html(title_raw_header, max_len=90)
            else:
                title_html = "" if is_virtual_collection else "<em>(Untitled)</em>"

        if title_html:
            title_line_html = f"""
          <div class="entry-title-line" style="display:flex; align-items:center; flex-wrap:wrap; gap:0; margin-top:2px; color:#374151; font-size:0.92rem; font-weight:500; line-height:1.25;">
            {date_chip}{title_html}
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
                rr.get("rism_publisher_printer_raw",""),
                rr.get("rism_publication_place_raw",""),
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
            (
                (
                    records[z]["instr_rism_main_raw"] + " " +
                    records[z]["instr_rism_alt_raw"] + " " +
                    records[z]["instr_catalogs_raw"] + " " +
                    records[z].get("search_tool_terms_raw", "")
                ).strip()
            )
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
        organology_payload = piece_value_payload(
            records,
            data_piece_ids,
            lambda rr: rr.get("organology_codes_keys", []),
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
      data-organology-pieces="{json_attr(organology_payload)}"
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
            <span class="{primary_class}" style="{primary_style}">
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
        .replace("@@LIBRARY_OPTIONS@@", library_options_js)
        .replace("@@ORGANOLOGY_OPTIONS@@", organology_options_js),
        encoding="utf-8"
    )

    # =========================
    # DETAIL PAGES
    # =========================
    for zid, rec in records.items():
        used_links_page = set()

        gid = rec["group"]
        ids_in_group = groups.get(gid, [zid])
        coll_id = next((x for x in ids_in_group if x in records and is_real_collection_record(records[x])), None)
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

        main_panel_html = detail_work_or_collection_panel_html(rec, ids_in_group, coll_id, is_virtual_group, records)
        source_panel_html = detail_source_panel_html(rec)
        rism_record_html = detail_rism_record_html(rec)
        catalogue_bibliography_html = detail_catalogue_bibliography_html(rec)
        note_html = detail_note_html(rec)
        org_html = detail_organology_html(rec)
        conc_html = detail_concordances_html(rec, records, used_links_page)

        detail_display_id = group_id(zid) if (detail_is_collection_record(rec) and clean_str(zid).endswith("/0")) else zid

        title_full = f"{zid} — {rec['title_raw'] or '(Untitled)'}"
        page_html = (
            detail_template
            .replace("@@TITLE_FULL@@", html.escape(title_full, quote=False))
            .replace("@@HEADER@@", build_header_html())
            .replace("@@BREADCRUMB@@", breadcrumb_extra)
            .replace("@@PARENT_BTN@@", parent_btn)
            .replace("@@ID@@", escape_textnode(detail_display_id))
            .replace("@@TAGS@@", tags_html)
            .replace("@@MAIN_PANEL@@", main_panel_html)
            .replace("@@SOURCE_PANEL@@", source_panel_html)
            .replace("@@RISM_RECORD@@", rism_record_html)
            .replace("@@CATALOGUE_BIBLIOGRAPHY@@", catalogue_bibliography_html)
            .replace("@@NOTE@@", note_html)
            .replace("@@ORG@@", org_html)
            .replace("@@CONC@@", conc_html)
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
    print("Organology instrument codes indexed:", len(organology_options))

if __name__ == "__main__":
    main()
