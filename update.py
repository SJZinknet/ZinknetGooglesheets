from pathlib import Path
import re

path = Path("generator/build.py")
txt = path.read_text(encoding="utf-8")

backup = path.with_suffix(".py.bak_search_sections")
backup.write_text(txt, encoding="utf-8")

# ============================================================
# 1) Replace the left Search & filters panel inside index_template
# ============================================================

new_search_panel = r'''    <section class="card search-card">
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
              <input id="searchInput" type="text" placeholder="Composer, title, number, library, RISM…" />
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
                <label for="biblioMode">Match mode</label>
                <select id="biblioMode">
                  <option value="any">Match any selected reference</option>
                  <option value="all">Match all selected references</option>
                </select>
              </div>

              <div class="filter-field">
                <label>References</label>
                <div id="biblioChoices" class="multi-choice-box"></div>
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
                <label for="holdingsMode">Match mode</label>
                <select id="holdingsMode">
                  <option value="any">Match any selected siglum</option>
                  <option value="all">Match all selected sigla</option>
                </select>
              </div>

              <div class="filter-field">
                <label>Sigla</label>
                <div id="holdingsChoices" class="multi-choice-box"></div>
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
                <input id="rismNoInput" type="text" placeholder="e.g. 990000327" />
              </div>
            </div>
          </details>

        </div>
      </div>
    </section>'''

pattern = re.compile(
    r'''    <section class="card">\s*
      <h2>Search & filters</h2>.*?
    </section>

    <section class="card">''',
    re.DOTALL
)

txt2, n = pattern.subn(new_search_panel + "\n\n    <section class=\"card\">", txt, count=1)

if n != 1:
    raise RuntimeError(
        "Search panel replacement failed. The Search & filters block was not found exactly once."
    )

txt = txt2

# ============================================================
# 2) Add CSS for the new collapsible search UI
# ============================================================

css_block = r'''

/* Search panel — collapsible sections */
.search-card-header{
  align-items:flex-start;
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
  border:1px solid rgba(208,213,235,0.95);
  background:linear-gradient(180deg,#fbfcff,#f6f7ff);
  border-radius:16px;
  overflow:hidden;
}

details.filter-section[open]{
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
  max-height:240px;
  overflow:auto;
  z-index:50;
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

.multi-choice-box{
  max-height:180px;
  overflow:auto;
  border:1px solid var(--border-subtle);
  background:#fafaff;
  border-radius:14px;
  padding:7px;
  display:flex;
  flex-direction:column;
  gap:4px;
}

.multi-choice-row{
  display:flex;
  gap:7px;
  align-items:flex-start;
  padding:5px 6px;
  border-radius:10px;
  font-size:.84rem;
  color:#374151;
}

.multi-choice-row:hover{
  background:#fff;
}

.multi-choice-row input{
  margin-top:2px;
}
'''

if "/* Search panel — collapsible sections */" not in txt:
    marker = ".entries {"
    pos = txt.find(marker)
    if pos == -1:
        raise RuntimeError("CSS insertion failed. Could not find '.entries {' marker.")
    txt = txt[:pos] + css_block + "\n" + txt[pos:]

# ============================================================
# 3) Add instrumentation suggestion dropdown JS
# ============================================================

# Insert JS helper after SEARCH_TOOL_INSTRS has populated stInstr.
js_marker = r'''  SEARCH_TOOL_INSTRS.forEach(o => {
    const opt = document.createElement('option');
    opt.value = o.k;
    opt.textContent = `${o.k} (${o.n})`;
    stInstr.appendChild(opt);
  });
'''

js_insert = r'''
  // ============ Instrumentation simple-search dropdown
  const instrMenu = document.getElementById('instrMenu');
  const instrList = document.getElementById('instrList');

  function closeInstrMenu(){
    if(!instrMenu || !instrList) return;
    instrMenu.style.display = 'none';
    instrList.innerHTML = '';
  }

  function openInstrMenu(items){
    if(!instrMenu || !instrList) return;
    instrList.innerHTML = '';

    items.forEach(obj => {
      const div = document.createElement('div');
      div.className = 'instr-item';

      const label = document.createElement('span');
      label.textContent = obj.k;

      const count = document.createElement('span');
      count.className = 'instr-item-count';
      count.textContent = obj.n;

      div.appendChild(label);
      div.appendChild(count);

      div.addEventListener('click', () => {
        instrInput.value = obj.k;
        closeInstrMenu();
        applyFilters();
      });

      instrList.appendChild(div);
    });

    instrMenu.style.display = items.length ? 'block' : 'none';
  }

  function computeInstrHits(){
    const q = normalize(instrInput.value).trim();
    if(!q) return SEARCH_TOOL_INSTRS.slice(0, 30);

    const hits = [];
    for(const obj of SEARCH_TOOL_INSTRS){
      const k = normalize(obj.k || '');
      if(k.includes(q)){
        hits.push(obj);
        if(hits.length >= 30) break;
      }
    }
    return hits;
  }

  instrInput.addEventListener('focus', () => {
    const hits = computeInstrHits();
    if(hits.length) openInstrMenu(hits);
  });

  instrInput.addEventListener('input', () => {
    const hits = computeInstrHits();
    if(hits.length) openInstrMenu(hits);
    else closeInstrMenu();
  });

  document.addEventListener('click', (ev) => {
    if(instrMenu && !instrMenu.contains(ev.target) && ev.target !== instrInput){
      closeInstrMenu();
    }
  });
'''

if "Instrumentation simple-search dropdown" not in txt:
    if js_marker not in txt:
        raise RuntimeError("JS insertion failed. Could not find SEARCH_TOOL_INSTRS population block.")
    txt = txt.replace(js_marker, js_marker + js_insert, 1)

# ============================================================
# 4) Remove duplicate old instrInput event listener if present?
# Keep it: it still applies filters while typing. The new listener only adds suggestions.
# ============================================================

path.write_text(txt, encoding="utf-8")

print("✅ Patch applied to generator/build.py")
print(f"Backup created: {backup}")
