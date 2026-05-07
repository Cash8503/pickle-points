// ──────────────────────────────────────────────────────────────────
// State
// ──────────────────────────────────────────────────────────────────
let cfg = null;
let pageIdx = 0;
let itemIdx = null;
let earnReasonIdx = null;
let earnNoteIdx = null;
let selectedTagName = null;

// ──────────────────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────────────────
async function boot() {
  setStatus('Loading config…');
  const r = await fetch('/api/config');
  cfg = await r.json();
  populateSettings();
  renderPages();
  renderTagSwatches();
  setPageIdx(0);
  setStatus('Ready');
}

// ──────────────────────────────────────────────────────────────────
// Status
// ──────────────────────────────────────────────────────────────────
function setStatus(msg, isError) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.color = isError ? '#ff6b6b' : '#aaa';
}

// ──────────────────────────────────────────────────────────────────
// Tab switching (left panel)
// ──────────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name + '-btn').classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

// ──────────────────────────────────────────────────────────────────
// Settings
// ──────────────────────────────────────────────────────────────────
function populateSettings() {
  const s = cfg.settings || {};
  document.getElementById('s-price-per-pickle').value =
    s.price_per_pickle ?? s.price_per_point ?? 0.50;
  document.getElementById('s-pickle-value').value =
    s.pickle_pickle_value ?? s.pickle_point_value ?? 1;
  document.getElementById('s-concurrency').value = s.fetch_concurrency ?? 5;
  document.getElementById('s-pdf-title').value   = cfg.pdf_title || '';
  document.getElementById('s-output-path').value = cfg.output_path || '';
}

function collectSettings() {
  cfg.settings = cfg.settings || {};
  cfg.settings.price_per_pickle   = parseFloat(document.getElementById('s-price-per-pickle').value) || 0.50;
  cfg.settings.pickle_pickle_value= parseInt(document.getElementById('s-pickle-value').value) || 1;
  cfg.settings.fetch_concurrency  = parseInt(document.getElementById('s-concurrency').value) || 5;
  cfg.pdf_title   = document.getElementById('s-pdf-title').value.trim();
  cfg.output_path = document.getElementById('s-output-path').value.trim();
  // Remove legacy keys so config stays clean
  delete cfg.settings.price_per_point;
  delete cfg.settings.pickle_point_value;
}

// ──────────────────────────────────────────────────────────────────
// Pages list
// ──────────────────────────────────────────────────────────────────
function renderPages() {
  const el = document.getElementById('pages-list');
  el.innerHTML = '';
  (cfg.pages || []).forEach((p, i) => {
    const div = document.createElement('div');
    div.className = 'page-item' + (i === pageIdx ? ' selected' : '');
    div.textContent = (p.title || `Page ${i+1}`) + (p.type === 'earn' ? ' [earn]' : '');
    div.onclick = () => setPageIdx(i);
    el.appendChild(div);
  });
}

function setPageIdx(i) {
  pageIdx = i;
  itemIdx = null;
  earnReasonIdx = null;
  earnNoteIdx = null;
  renderPages();
  loadPageSettings();
  renderItems();
  showNoItem();
}

function addPage() {
  cfg.pages = cfg.pages || [];
  cfg.pages.push({
    title: 'New Page', subtitle: '', section_label: '',
    accent: '#DA291C', items: [], layout: { cols: 4 }
  });
  setPageIdx(cfg.pages.length - 1);
  scheduleSave();
}

function delPage() {
  const pages = cfg.pages || [];
  if (!pages.length) return;
  if (!confirm(`Delete page "${pages[pageIdx]?.title || ''}"?`)) return;
  pages.splice(pageIdx, 1);
  const ni = Math.max(0, pageIdx - 1);
  cfg.pages = pages;
  setPageIdx(ni);
  scheduleSave();
}

function movePage(d) {
  const pages = cfg.pages || [];
  const ni = pageIdx + d;
  if (ni < 0 || ni >= pages.length) return;
  [pages[pageIdx], pages[ni]] = [pages[ni], pages[pageIdx]];
  pageIdx = ni;
  renderPages();
  scheduleSave();
}

// ──────────────────────────────────────────────────────────────────
// Page settings form
// ──────────────────────────────────────────────────────────────────
function loadPageSettings() {
  const page = currentPage();
  if (!page) return;
  document.getElementById('pg-title').value    = page.title || '';
  document.getElementById('pg-subtitle').value = page.subtitle || '';
  document.getElementById('pg-section').value  = page.section_label || '';
  const accent = page.accent || '#DA291C';
  document.getElementById('pg-accent-color').value = accent;
  document.getElementById('pg-accent-text').value  = accent;
  const lay = page.layout || {};
  document.getElementById('pg-cols').value   = lay.cols ?? 4;
  document.getElementById('pg-cardh').value  = lay.card_h ?? 126;
  document.getElementById('pg-gutter').value = lay.gutter ?? 12;
  const type = page.type || 'merch';
  document.getElementById('pg-type').value = type;
  togglePageType(type);
  if (type === 'earn') {
    document.getElementById('pg-earn-headline').value = page.earn_headline || '';
    renderEarnReasons();
    renderEarnNotes();
  }
}

function syncAccentFromPicker() {
  const v = document.getElementById('pg-accent-color').value;
  document.getElementById('pg-accent-text').value = v.toUpperCase();
}

function syncAccentFromText() {
  const v = document.getElementById('pg-accent-text').value.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(v)) {
    document.getElementById('pg-accent-color').value = v;
  }
}

function applyPageSettings() {
  const page = currentPage();
  if (!page) return;
  page.title         = document.getElementById('pg-title').value;
  page.subtitle      = document.getElementById('pg-subtitle').value;
  page.section_label = document.getElementById('pg-section').value;
  page.accent        = document.getElementById('pg-accent-text').value.trim() || '#DA291C';
  const cols   = parseInt(document.getElementById('pg-cols').value) || 4;
  const cardh  = parseInt(document.getElementById('pg-cardh').value) || 126;
  const gutter = parseInt(document.getElementById('pg-gutter').value) || 12;
  page.layout = { cols };
  if (cardh  !== 126) page.layout.card_h  = cardh;
  if (gutter !== 12)  page.layout.gutter  = gutter;
  const type = document.getElementById('pg-type').value;
  if (type === 'earn') { page.type = 'earn'; } else { delete page.type; }
  renderPages();
  scheduleSave();
}

// ──────────────────────────────────────────────────────────────────
// Items list
// ──────────────────────────────────────────────────────────────────
function renderItems() {
  const el = document.getElementById('items-list');
  el.innerHTML = '';
  const page = currentPage();
  if (!page) return;
  (page.items || []).forEach((item, i) => {
    const div = document.createElement('div');
    div.className = 'item-row' + (i === itemIdx ? ' selected' : '');
    div.onclick = () => selectItem(i);

    const badge = document.createElement('span');
    badge.className = 'item-badge ' + (item.type === 'smilemakers' ? 'badge-sm' : 'badge-man');
    badge.textContent = item.type === 'smilemakers' ? 'SM' : 'M';

    const name = document.createElement('span');
    name.className = 'item-name';
    if (item.type === 'smilemakers') {
      const u = (item.urls || [])[0] || '?';
      const slug = u.replace(/\/$/, '').split('/').pop();
      const extra = (item.urls || []).length > 1 ? ` +${item.urls.length-1}` : '';
      name.textContent = slug + extra + (item.tag ? ` [${item.tag}]` : '');
    } else {
      name.textContent = (item.name || '?') + (item.tag ? ` [${item.tag}]` : '');
    }
    div.appendChild(badge);
    div.appendChild(name);
    el.appendChild(div);
  });
}

function selectItem(i) {
  itemIdx = i;
  renderItems();
  buildItemEditor();
}

function addSmItem() {
  const page = currentPage();
  if (!page) return;
  page.items = page.items || [];
  page.items.push({ type: 'smilemakers', urls: ['https://smilemakersonline.com/'] });
  itemIdx = page.items.length - 1;
  renderItems();
  buildItemEditor();
  scheduleSave();
}

function addManualItem() {
  const page = currentPage();
  if (!page) return;
  page.items = page.items || [];
  page.items.push({ type: 'manual', name: 'New Item', desc: '', pickles: null, tag: null, image: '', variants: [] });
  itemIdx = page.items.length - 1;
  renderItems();
  buildItemEditor();
  scheduleSave();
}

function delItem() {
  const page = currentPage();
  if (!page || itemIdx === null) return;
  page.items.splice(itemIdx, 1);
  itemIdx = null;
  renderItems();
  showNoItem();
  scheduleSave();
}

function moveItem(d) {
  const page = currentPage();
  if (!page || itemIdx === null) return;
  const items = page.items || [];
  const ni = itemIdx + d;
  if (ni < 0 || ni >= items.length) return;
  [items[itemIdx], items[ni]] = [items[ni], items[itemIdx]];
  itemIdx = ni;
  renderItems();
  buildItemEditor();
  scheduleSave();
}

// ──────────────────────────────────────────────────────────────────
// Item editor
// ──────────────────────────────────────────────────────────────────
function showNoItem() {
  document.getElementById('no-item-msg').style.display = 'flex';
  document.getElementById('item-editor').style.display = 'none';
}

function buildItemEditor() {
  const page = currentPage();
  const item = page && itemIdx !== null ? (page.items || [])[itemIdx] : null;
  if (!item) { showNoItem(); return; }
  document.getElementById('no-item-msg').style.display = 'none';
  const ed = document.getElementById('item-editor');
  ed.style.display = 'block';
  ed.innerHTML = '';

  if (item.type === 'smilemakers') {
    buildSmEditor(ed, item);
  } else {
    buildManualEditor(ed, item);
  }
}

function buildSmEditor(ed, item) {
  const tags = ['', ...Object.keys(cfg.tag_colors || {})];
  ed.innerHTML = `
    <div class="editor-title">SmileMakers Item</div>
    <div class="ed-row">
      <label>URLs</label>
      <div style="flex:1">
        <div class="url-list-box">
          <select id="url-select" size="4" style="width:100%;border:none;font-family:monospace;font-size:10px"></select>
        </div>
        <input type="text" id="url-entry" placeholder="https://smilemakersonline.com/product/"
               style="width:100%;margin-top:4px;padding:4px 6px;border:1px solid var(--border);border-radius:3px;font-family:monospace;font-size:10px">
        <div class="url-actions">
          <button onclick="urlAdd()">Add</button>
          <button onclick="urlReplace()">Replace</button>
          <button onclick="urlRemove()">Remove</button>
          <button onclick="fetchUrlPreview()">Fetch Info</button>
        </div>
        <div id="fetch-status"></div>
        <div id="fetched-preview"></div>
      </div>
    </div>
    <div class="ed-row">
      <label>Tag</label>
      <select id="ed-tag" onchange="itemSet('tag', this.value || null)">
        ${tags.map(t => `<option value="${t}" ${item.tag===t?'selected':''}>${t||'(none)'}</option>`).join('')}
      </select>
    </div>
    <div class="ed-row">
      <label>Variants</label>
      <select id="ed-variant-type" onchange="itemSet('variant_type', this.value)">
        <option value="color" ${item.variant_type!=='sex'?'selected':''}>color</option>
        <option value="sex"   ${item.variant_type==='sex'?'selected':''}>sex</option>
      </select>
    </div>
    <hr class="ed-sep">
    <div class="overrides-note">Overrides — blank = auto from URL &nbsp;<span style="font-weight:400;color:#aaa">(fetch info to see placeholders)</span></div>
    <div class="ed-row">
      <label>Name</label>
      <div class="override-wrap">
        <input type="text" id="ed-name" value="${esc(item.name||'')}" placeholder="auto"
               oninput="itemSet('name', this.value||null)">
        ${item.name ? `<button class="clr-btn" onclick="clearOverride('name','ed-name')" title="Clear override">×</button>` : ''}
      </div>
    </div>
    <div class="ed-row">
      <label>Desc</label>
      <div class="override-wrap">
        <textarea id="ed-desc" placeholder="auto"
                  oninput="itemSet('desc', this.value||null)">${esc(item.desc||'')}</textarea>
        ${item.desc ? `<button class="clr-btn" onclick="clearOverride('desc','ed-desc')" title="Clear override">×</button>` : ''}
      </div>
    </div>
    <div class="ed-row">
      <label>Pickles</label>
      <div class="override-wrap">
        <input type="number" id="ed-pickles" min="0" placeholder="auto"
               value="${item.pickles??item.points??''}"
               oninput="itemSet('pickles', this.value?parseInt(this.value):null)">
        ${(item.pickles!=null||item.points!=null) ? `<button class="clr-btn" onclick="clearOverride('pickles','ed-pickles')" title="Clear override">×</button>` : ''}
      </div>
    </div>
    <div class="ed-row">
      <label>Image URL</label>
      <div class="override-wrap">
        <input type="text" id="ed-image" value="${esc(item.image||'')}" placeholder="auto"
               oninput="itemSet('image', this.value||null)">
        ${item.image ? `<button class="clr-btn" onclick="clearOverride('image','ed-image')" title="Clear override">×</button>` : ''}
      </div>
    </div>
  `;
  // Populate URL select
  refreshUrlSelect(item);
  // Double-click to load URL into entry
  document.getElementById('url-select').ondblclick = () => {
    const sel = document.getElementById('url-select');
    if (sel.selectedIndex >= 0)
      document.getElementById('url-entry').value = sel.options[sel.selectedIndex].value;
  };
}

function buildManualEditor(ed, item) {
  const tags = ['', ...Object.keys(cfg.tag_colors || {})];
  ed.innerHTML = `
    <div class="editor-title">Manual Item</div>
    <div class="ed-row">
      <label>Name</label>
      <input type="text" id="ed-name" value="${esc(item.name||'')}"
             oninput="itemSet('name', this.value)">
    </div>
    <div class="ed-row">
      <label>Desc</label>
      <textarea id="ed-desc" oninput="itemSet('desc', this.value||null)">${esc(item.desc||'')}</textarea>
    </div>
    <div class="ed-row">
      <label>Pickles</label>
      <input type="number" id="ed-pickles" min="0" value="${item.pickles??item.points??''}"
             oninput="itemSet('pickles', this.value?parseInt(this.value):null)">
    </div>
    <div class="ed-row">
      <label>Tag</label>
      <select id="ed-tag" onchange="itemSet('tag', this.value||null)">
        ${tags.map(t => `<option value="${t}" ${item.tag===t?'selected':''}>${t||'(none)'}</option>`).join('')}
      </select>
    </div>
    <div class="ed-row">
      <label>Image URL</label>
      <input type="text" id="ed-image" value="${esc(item.image||'')}"
             oninput="itemSet('image', this.value||null)">
    </div>
    <hr class="ed-sep">
    <div class="overrides-note">Variants (manual JSON array, e.g. [{"type":"size","value":"M"}])</div>
    <div class="ed-row">
      <label>Variants</label>
      <textarea id="ed-variants" oninput="setManualVariants(this.value)" style="font-family:monospace;font-size:10px">${JSON.stringify(item.variants||[])}</textarea>
    </div>
  `;
}

// ──────────────────────────────────────────────────────────────────
// Page type toggle
// ──────────────────────────────────────────────────────────────────
function togglePageType(type) {
  const isEarn = type === 'earn';
  document.getElementById('items-area').style.display = isEarn ? 'none' : '';
  document.getElementById('earn-area').style.display  = isEarn ? ''     : 'none';
  if (isEarn) showNoItem();
}

function onPageTypeChange() {
  const type = document.getElementById('pg-type').value;
  const page = currentPage();
  if (!page) return;
  if (type === 'earn') {
    page.type    = 'earn';
    page.reasons = page.reasons || [];
    page.notes   = page.notes   || [];
    document.getElementById('pg-earn-headline').value = page.earn_headline || '';
    renderEarnReasons();
    renderEarnNotes();
  } else {
    delete page.type;
  }
  togglePageType(type);
  renderPages();
  scheduleSave();
}

function earnHeadlineChange() {
  const page = currentPage();
  if (!page) return;
  page.earn_headline = document.getElementById('pg-earn-headline').value;
  scheduleSave();
}

// ──────────────────────────────────────────────────────────────────
// Earn reasons
// ──────────────────────────────────────────────────────────────────
function renderEarnReasons() {
  const page = currentPage();
  const el = document.getElementById('earn-reasons-list');
  if (!el || !page) return;
  el.innerHTML = '';
  (page.reasons || []).forEach((r, i) => {
    const div = document.createElement('div');
    div.className = 'item-row' + (i === earnReasonIdx ? ' selected' : '');
    div.onclick = () => selectEarnReason(i);
    div.innerHTML = `<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.label || '?')}</span>`
      + `<span style="font-weight:700;color:#DA291C;margin-left:6px">${r.value ?? ''}</span>`;
    el.appendChild(div);
  });
}

function selectEarnReason(i) {
  earnReasonIdx = i;
  earnNoteIdx   = null;
  renderEarnReasons();
  renderEarnNotes();
  buildEarnReasonEditor();
}

function buildEarnReasonEditor() {
  const page   = currentPage();
  const reason = page && earnReasonIdx !== null ? (page.reasons || [])[earnReasonIdx] : null;
  if (!reason) { showNoItem(); return; }
  document.getElementById('no-item-msg').style.display = 'none';
  const ed = document.getElementById('item-editor');
  ed.style.display = 'block';
  const rtype = reason.type || 'add';
  ed.innerHTML = `
    <div class="editor-title">Earn Reason</div>
    <div class="ed-row">
      <label>Label</label>
      <input type="text" id="er-label" value="${esc(reason.label || '')}"
             oninput="reasonSet('label', this.value)">
    </div>
    <div class="ed-row">
      <label>Type</label>
      <select id="er-type" onchange="reasonSet('type', this.value)">
        <option value="add"      ${rtype === 'add'      ? 'selected' : ''}>Add Points</option>
        <option value="multiply" ${rtype === 'multiply' ? 'selected' : ''}>Multiplier</option>
      </select>
    </div>
    <div class="ed-row">
      <label>Value</label>
      <input type="number" id="er-value" value="${reason.value ?? ''}"
             oninput="reasonSet('value', this.value !== '' ? parseInt(this.value) : 0)">
    </div>
    <div class="ed-row">
      <label>Scope</label>
      <input type="text" id="er-scope" value="${esc(reason.scope || '')}"
             placeholder="e.g. Whole store, Peaks only…"
             oninput="reasonSet('scope', this.value || null)">
    </div>`;
}

function reasonSet(key, val) {
  const page   = currentPage();
  const reason = page && earnReasonIdx !== null ? (page.reasons || [])[earnReasonIdx] : null;
  if (!reason) return;
  reason[key] = val;
  renderEarnReasons();
  scheduleSave();
}

function addEarnReason() {
  const page = currentPage();
  if (!page) return;
  page.reasons = page.reasons || [];
  page.reasons.push({ label: 'New Reason', value: 5 });
  earnReasonIdx = page.reasons.length - 1;
  renderEarnReasons();
  buildEarnReasonEditor();
  scheduleSave();
}

function delEarnReason() {
  const page = currentPage();
  if (!page || earnReasonIdx === null) return;
  page.reasons.splice(earnReasonIdx, 1);
  earnReasonIdx = null;
  renderEarnReasons();
  showNoItem();
  scheduleSave();
}

function moveEarnReason(d) {
  const page = currentPage();
  if (!page || earnReasonIdx === null) return;
  const arr = page.reasons || [];
  const ni  = earnReasonIdx + d;
  if (ni < 0 || ni >= arr.length) return;
  [arr[earnReasonIdx], arr[ni]] = [arr[ni], arr[earnReasonIdx]];
  earnReasonIdx = ni;
  renderEarnReasons();
  buildEarnReasonEditor();
  scheduleSave();
}

// ──────────────────────────────────────────────────────────────────
// Earn notes
// ──────────────────────────────────────────────────────────────────
function renderEarnNotes() {
  const page = currentPage();
  const el = document.getElementById('earn-notes-list');
  if (!el || !page) return;
  el.innerHTML = '';
  (page.notes || []).forEach((note, i) => {
    const div = document.createElement('div');
    div.className = 'item-row' + (i === earnNoteIdx ? ' selected' : '');
    div.onclick = () => selectEarnNote(i);
    const span = document.createElement('span');
    span.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
    span.textContent = note || '(empty)';
    div.appendChild(span);
    el.appendChild(div);
  });
}

function selectEarnNote(i) {
  earnNoteIdx   = i;
  earnReasonIdx = null;
  renderEarnReasons();
  renderEarnNotes();
  buildEarnNoteEditor();
}

function buildEarnNoteEditor() {
  const page = currentPage();
  const note = page && earnNoteIdx !== null ? (page.notes || [])[earnNoteIdx] : null;
  if (note === null || note === undefined) { showNoItem(); return; }
  document.getElementById('no-item-msg').style.display = 'none';
  const ed = document.getElementById('item-editor');
  ed.style.display = 'block';
  ed.innerHTML = `
    <div class="editor-title">Note</div>
    <div class="ed-row">
      <label>Text</label>
      <textarea id="en-text" oninput="noteSet(this.value)">${esc(note)}</textarea>
    </div>`;
}

function noteSet(val) {
  const page = currentPage();
  if (!page || earnNoteIdx === null) return;
  page.notes[earnNoteIdx] = val;
  renderEarnNotes();
  scheduleSave();
}

function addEarnNote() {
  const page = currentPage();
  if (!page) return;
  page.notes = page.notes || [];
  page.notes.push('New note');
  earnNoteIdx = page.notes.length - 1;
  renderEarnNotes();
  buildEarnNoteEditor();
  scheduleSave();
}

function delEarnNote() {
  const page = currentPage();
  if (!page || earnNoteIdx === null) return;
  page.notes.splice(earnNoteIdx, 1);
  earnNoteIdx = null;
  renderEarnNotes();
  showNoItem();
  scheduleSave();
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function itemSet(key, val) {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item) return;
  if (val === null || val === undefined || val === '') {
    delete item[key];
  } else {
    item[key] = val;
  }
  renderItems();
  scheduleSave();
}

function setManualVariants(val) {
  try {
    const v = JSON.parse(val);
    itemSet('variants', Array.isArray(v) ? v : []);
  } catch(e) { /* invalid JSON while typing, ignore */ }
}

function refreshUrlSelect(item) {
  const sel = document.getElementById('url-select');
  if (!sel) return;
  sel.innerHTML = '';
  (item.urls || []).forEach(u => {
    const opt = document.createElement('option');
    opt.value = u; opt.textContent = u;
    sel.appendChild(opt);
  });
}

function urlAdd() {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item) return;
  const u = document.getElementById('url-entry').value.trim();
  if (!u) return;
  item.urls = item.urls || [];
  item.urls.push(u);
  document.getElementById('url-entry').value = '';
  refreshUrlSelect(item);
  renderItems();
}

function urlReplace() {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item) return;
  const sel = document.getElementById('url-select');
  const u   = document.getElementById('url-entry').value.trim();
  if (sel.selectedIndex < 0 || !u) return;
  item.urls[sel.selectedIndex] = u;
  refreshUrlSelect(item);
  renderItems();
}

function urlRemove() {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item) return;
  const sel = document.getElementById('url-select');
  if (sel.selectedIndex < 0) return;
  item.urls.splice(sel.selectedIndex, 1);
  refreshUrlSelect(item);
  renderItems();
}

function clearOverride(key, inputId) {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item) return;
  delete item[key];
  delete item['points']; // also clear legacy alias if clearing pickles
  const el = document.getElementById(inputId);
  if (el) el.value = '';
  buildItemEditor();   // rebuild to remove the × button
  scheduleSave();
}

async function fetchUrlPreview() {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item) return;
  const sel = document.getElementById('url-select');
  const u = sel.selectedIndex >= 0
    ? sel.options[sel.selectedIndex].value
    : document.getElementById('url-entry').value.trim();
  if (!u) return;
  const statusEl = document.getElementById('fetch-status');
  statusEl.textContent = 'Fetching…';
  try {
    const r = await fetch('/api/fetch-product', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url: u})
    });
    const d = await r.json();
    if (d.error) { statusEl.textContent = 'Error: ' + d.error; return; }

    // Show fetched data as placeholder text on override inputs (not as values).
    // Only fields that have no active override get the placeholder updated.
    const nameEl    = document.getElementById('ed-name');
    const descEl    = document.getElementById('ed-desc');
    const picklesEl = document.getElementById('ed-pickles');
    const imageEl   = document.getElementById('ed-image');
    if (nameEl    && !nameEl.value)    nameEl.placeholder    = d.name  || 'auto';
    if (descEl    && !descEl.value)    descEl.placeholder    = d.desc  || 'auto';
    if (picklesEl && !picklesEl.value) picklesEl.placeholder = d.price ? `auto (~${Math.ceil(d.price / (cfg.settings?.price_per_pickle || 0.5))} pickles)` : 'auto';
    if (imageEl   && !imageEl.value)   imageEl.placeholder   = d.image || 'auto';

    const sizes = d.sizes && d.sizes.length ? `  •  sizes: ${d.sizes.join(', ')}` : '';
    statusEl.textContent = `Fetched ✓  $${d.price ? d.price.toFixed(2) : '?'}${sizes}`;
  } catch(e) {
    statusEl.textContent = 'Network error';
  }
}

// ──────────────────────────────────────────────────────────────────
// Tag swatches (bottom bar)
// ──────────────────────────────────────────────────────────────────
function renderTagSwatches() {
  const el = document.getElementById('tag-swatches');
  el.innerHTML = '';
  Object.entries(cfg.tag_colors || {}).forEach(([tag, cols]) => {
    const div = document.createElement('div');
    div.className = 'tag-swatch-item';
    div.innerHTML = `
      <span class="swatch-dot" style="background:${cols.bg};border-color:${cols.text}"></span>
      <span style="color:${cols.text};font-weight:700;font-size:11px">${tag}</span>`;
    el.appendChild(div);
  });
}

// ──────────────────────────────────────────────────────────────────
// Tag manager modal
// ──────────────────────────────────────────────────────────────────
function openTagManager() {
  document.getElementById('tag-modal').style.display = 'flex';
  selectedTagName = null;
  renderTagMgrList();
}

function closeTagModal(e) {
  if (e.target === document.getElementById('tag-modal'))
    document.getElementById('tag-modal').style.display = 'none';
}

function renderTagMgrList() {
  const el = document.getElementById('tag-mgr-list');
  el.innerHTML = '';
  Object.keys(cfg.tag_colors || {}).forEach(tag => {
    const div = document.createElement('div');
    div.className = 'tag-mgr-item' + (tag === selectedTagName ? ' selected' : '');
    div.textContent = tag;
    div.onclick = () => { selectedTagName = tag; renderTagMgrList(); loadTagEditor(); };
    el.appendChild(div);
  });
}

function loadTagEditor() {
  if (!selectedTagName) return;
  const cols = cfg.tag_colors[selectedTagName];
  document.getElementById('tag-edit-title').textContent = selectedTagName;
  document.getElementById('tag-bg-picker').value  = cols.bg;
  document.getElementById('tag-bg-text').value    = cols.bg;
  document.getElementById('tag-txt-picker').value = cols.text;
  document.getElementById('tag-txt-text').value   = cols.text;
}

function syncTagColor(which) {
  if (!selectedTagName) return;
  const val = which === 'bg'
    ? document.getElementById('tag-bg-picker').value
    : document.getElementById('tag-txt-picker').value;
  cfg.tag_colors[selectedTagName][which] = val.toUpperCase();
  if (which === 'bg')   document.getElementById('tag-bg-text').value  = val.toUpperCase();
  if (which === 'text') document.getElementById('tag-txt-text').value = val.toUpperCase();
  renderTagSwatches();
}

function syncTagColorText(which) {
  if (!selectedTagName) return;
  const val = which === 'bg'
    ? document.getElementById('tag-bg-text').value.trim()
    : document.getElementById('tag-txt-text').value.trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(val)) return;
  cfg.tag_colors[selectedTagName][which] = val.toUpperCase();
  if (which === 'bg')   document.getElementById('tag-bg-picker').value  = val;
  if (which === 'text') document.getElementById('tag-txt-picker').value = val;
  renderTagSwatches();
}

function addTag() {
  const name = prompt('Tag name (will be uppercased):');
  if (!name) return;
  const upper = name.trim().toUpperCase();
  if (!upper) return;
  if (cfg.tag_colors[upper]) { alert('Tag already exists!'); return; }
  cfg.tag_colors[upper] = { bg: '#FFFFFF', text: '#000000' };
  selectedTagName = upper;
  renderTagMgrList();
  loadTagEditor();
  renderTagSwatches();
}

function deleteTag() {
  if (!selectedTagName) return;
  if (!confirm(`Delete tag "${selectedTagName}"?`)) return;
  delete cfg.tag_colors[selectedTagName];
  selectedTagName = null;
  document.getElementById('tag-edit-title').textContent = 'Select a tag';
  renderTagMgrList();
  renderTagSwatches();
}

// ──────────────────────────────────────────────────────────────────
// Save / Preview
// ──────────────────────────────────────────────────────────────────
async function saveConfig() {
  collectSettings();
  setStatus('Saving…');
  try {
    const r = await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(cfg)
    });
    const d = await r.json();
    if (d.ok) {
      setStatus('Saved ✓');
      setTimeout(() => setStatus('Ready'), 2500);
      reloadPreview();
    } else {
      setStatus('Save failed: ' + (d.error || '?'), true);
    }
  } catch(e) {
    setStatus('Network error', true);
  }
}

// Auto-save: debounce 700ms after any change, then save + refresh preview.
let _saveTimer = null;
function scheduleSave() {
  clearTimeout(_saveTimer);
  setStatus('Unsaved changes…');
  _saveTimer = setTimeout(() => saveConfig(), 700);
}

// Settings-only save: update cfg immediately, debounce the disk write, no preview reload.
let _settingsTimer = null;
async function scheduleSettingsSave() {
  collectSettings();   // update cfg in memory RIGHT NOW so switching items never loses data
  clearTimeout(_settingsTimer);
  setStatus('Unsaved changes…');
  _settingsTimer = setTimeout(async () => {
    collectSettings(); // re-collect at write time in case of rapid changes
    setStatus('Saving…');
    try {
      const r = await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(cfg)
      });
      const d = await r.json();
      if (d.ok) {
        setStatus('Saved ✓');
        setTimeout(() => setStatus('Ready'), 2500);
      } else {
        setStatus('Save failed: ' + (d.error || '?'), true);
      }
    } catch(e) {
      setStatus('Network error', true);
    }
  }, 900);
}

function reloadPreview() {
  const f = document.getElementById('preview-frame');
  const s = document.getElementById('preview-status');
  const previousScroll = getPreviewScroll(f);
  if (s) s.textContent = 'Refreshing…';
  f.addEventListener('load', () => {
    restorePreviewScroll(f, previousScroll);
  }, { once: true });
  f.src = '/preview-frame?t=' + Date.now();
  f.onload = () => { if (s) s.textContent = 'Live preview'; };
}

function openPreview() {
  window.open('/preview', '_blank');
}

function getPreviewScroll(frame) {
  try {
    const win = frame && frame.contentWindow;
    return win ? { x: win.scrollX || 0, y: win.scrollY || 0 } : { x: 0, y: 0 };
  } catch(e) {
    return { x: 0, y: 0 };
  }
}

function restorePreviewScroll(frame, pos) {
  try {
    const win = frame && frame.contentWindow;
    if (!win || !pos) return;
    win.requestAnimationFrame(() => {
      win.scrollTo(pos.x, pos.y);
      setTimeout(() => win.scrollTo(pos.x, pos.y), 75);
    });
  } catch(e) { /* Ignore cross-frame timing issues while preview reloads. */ }
}

// Drag-to-resize the preview panel
(function() {
  const handle = document.getElementById('drag-handle');
  const right  = document.getElementById('right-panel');
  const prev   = document.getElementById('preview-panel');
  if (!handle) return;
  let startX, startRW, startPW;
  handle.addEventListener('mousedown', e => {
    startX  = e.clientX;
    startRW = right.offsetWidth;
    startPW = prev.offsetWidth;
    handle.classList.add('dragging');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
    e.preventDefault();
  });
  function onMove(e) {
    const dx = e.clientX - startX;
    const rw = Math.max(240, startRW + dx);
    const pw = Math.max(200, startPW - dx);
    right.style.flex = 'none';
    right.style.width = rw + 'px';
    prev.style.flex = 'none';
    prev.style.width = pw + 'px';
  }
  function onUp() {
    handle.classList.remove('dragging');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup',   onUp);
  }
})();

// ──────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────
function currentPage() {
  return (cfg && cfg.pages && cfg.pages[pageIdx]) || null;
}

// Boot
boot();