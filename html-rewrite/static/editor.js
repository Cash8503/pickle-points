// ──────────────────────────────────────────────────────────────────
// State
// ──────────────────────────────────────────────────────────────────
let cfg = null;
let pageIdx = 0;
let itemIdx = null;
let earnReasonIdx = null;
let earnNoteIdx = null;
let selectedTagName = null;
let previewSelectedOnly = false;
let itemFilterText = '';
let userDarkMode = !!window.PICKLE_USER_DARK_MODE;
let hasUnsavedChanges = false;
let saveInFlight = false;

// ──────────────────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────────────────
async function boot() {
  setStatus('Loading config\u2026');
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
function setStatus(msg, state) {
  const el = document.getElementById('status');
  el.textContent = msg;
  const colors = { ok: '#52b788', warn: '#e8a000', err: '#ff6b6b' };
  el.style.color = colors[state] ?? (state === true ? colors.err : '#aaa');
}

function markDirty() {
  hasUnsavedChanges = true;
}

function hasPendingSave() {
  return hasUnsavedChanges || !!_saveTimer || !!_settingsTimer || saveInFlight;
}

function markCleanIfIdle() {
  if (!_saveTimer && !_settingsTimer && !saveInFlight) {
    hasUnsavedChanges = false;
  }
}

function confirmDiscardUnsavedChanges() {
  if (!hasPendingSave()) return true;
  return window.confirm('You have unsaved changes that may still be saving. Leave this page anyway?');
}

function wireUnsavedNavigationGuard() {
  window.addEventListener('beforeunload', event => {
    if (!hasPendingSave()) return;
    event.preventDefault();
    event.returnValue = '';
  });

  document.querySelectorAll('a[href]').forEach(link => {
    if (link.target === '_blank') return;
    link.addEventListener('click', event => {
      if (!confirmDiscardUnsavedChanges()) {
        event.preventDefault();
      }
    });
  });

  const switcher = document.getElementById('store-switcher');
  if (switcher) {
    switcher.addEventListener('submit', event => {
      if (!confirmDiscardUnsavedChanges()) {
        event.preventDefault();
      }
    });
  }
}

function submitStoreSwitcher(select) {
  if (!confirmDiscardUnsavedChanges()) {
    select.value = window.PICKLE_STORE_NUM || select.querySelector('option[selected]')?.value || select.value;
    return;
  }
  select.form.submit();
}

function showUndoToast(message, onUndo) {
  let wrap = document.getElementById('undo-toast-wrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'undo-toast-wrap';
    document.body.appendChild(wrap);
  }
  const toast = document.createElement('div');
  toast.className = 'undo-toast';
  const msg = document.createElement('span');
  msg.textContent = message;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = 'Undo';
  toast.appendChild(msg);
  toast.appendChild(btn);
  wrap.appendChild(toast);
  while (wrap.children.length > 3) {
    wrap.firstElementChild.remove();
  }

  const close = () => {
    clearTimeout(timer);
    toast.remove();
  };
  const timer = setTimeout(close, 7000);
  btn.onclick = () => {
    close();
    onUndo();
  };
}

function moveInArray(arr, from, to) {
  if (!arr || from === to || from < 0 || to < 0 || from >= arr.length || to >= arr.length) return false;
  const [item] = arr.splice(from, 1);
  arr.splice(to, 0, item);
  return true;
}

function wireDragRow(row, listKey, index, onMove) {
  row.draggable = true;
  row.addEventListener('dragstart', event => {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(index));
    event.dataTransfer.setData('application/x-pickle-list', listKey);
    row.classList.add('dragging');
  });
  row.addEventListener('dragend', () => {
    row.classList.remove('dragging');
    row.classList.remove('drag-over');
  });
  row.addEventListener('dragover', event => {
    event.preventDefault();
    row.classList.add('drag-over');
  });
  row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
  row.addEventListener('drop', event => {
    event.preventDefault();
    row.classList.remove('drag-over');
    if (event.dataTransfer.getData('application/x-pickle-list') !== listKey) return;
    const from = parseInt(event.dataTransfer.getData('text/plain'), 10);
    if (Number.isNaN(from)) return;
    onMove(from, index);
  });
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
  // Defaults mirror config_schema.py; saved configs should use the normalized keys.
  document.getElementById('s-price-per-pickle').value =
    s.price_per_pickle ?? s.price_per_point ?? 0.50;
  document.getElementById('s-pickle-value').value =
    s.pickle_chip_value ?? s.pickle_pickle_value ?? s.pickle_point_value ?? 1;
  document.getElementById('s-concurrency').value = s.fetch_concurrency ?? 5;
  document.getElementById('s-dark-mode').checked = userDarkMode;
  document.getElementById('s-pdf-title').value   = cfg.pdf_title || '';
  document.getElementById('s-output-path').value = cfg.output_path || '';
  applyTheme();
}

function collectSettings() {
  cfg.settings = cfg.settings || {};
  cfg.settings.price_per_pickle   = parseFloat(document.getElementById('s-price-per-pickle').value) || 0.50;
  cfg.settings.pickle_chip_value  = parseInt(document.getElementById('s-pickle-value').value) || 1;
  cfg.settings.fetch_concurrency  = parseInt(document.getElementById('s-concurrency').value) || 5;
  cfg.pdf_title   = document.getElementById('s-pdf-title').value.trim();
  cfg.output_path = document.getElementById('s-output-path').value.trim();
  // Remove legacy keys so config stays clean
  delete cfg.settings.price_per_point;
  delete cfg.settings.pickle_point_value;
  delete cfg.settings.pickle_pickle_value;
  delete cfg.settings.dark_mode;
}

function applyTheme() {
  document.body.classList.toggle('dark-mode', userDarkMode);
}

function toggleDarkMode() {
  userDarkMode = !!document.getElementById('s-dark-mode')?.checked;
  applyTheme();
  saveDarkModePreference(userDarkMode);
}

async function saveDarkModePreference(enabled) {
  const body = new URLSearchParams({
    csrf_token: window.PICKLE_CSRF_TOKEN || document.querySelector('meta[name="csrf-token"]')?.content || '',
    dark_mode: enabled ? '1' : '0',
    ajax: '1',
  });
  try {
    const r = await fetch('/user/dark-mode', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.ok) throw new Error(data.error || 'Theme preference failed to save');
    setStatus('Theme saved', 'ok');
  } catch (err) {
    setStatus(err.message || 'Theme preference failed to save', 'err');
  }
}

// ──────────────────────────────────────────────────────────────────
// Context menu
// ──────────────────────────────────────────────────────────────────
function showCtxMenu(x, y, menuItems) {
  const menu = document.getElementById('ctx-menu');
  menu.innerHTML = '';
  menuItems.forEach(item => {
    if (item === 'sep') {
      const hr = document.createElement('div');
      hr.className = 'ctx-sep';
      menu.appendChild(hr);
      return;
    }
    const btn = document.createElement('button');
    btn.className = 'ctx-item' + (item.danger ? ' ctx-danger' : '');
    btn.textContent = item.label;
    btn.onclick = () => { hideCtxMenu(); item.action(); };
    menu.appendChild(btn);
  });
  menu.style.display = 'block';
  const mw = menu.offsetWidth || 170;
  const mh = menu.offsetHeight || menuItems.length * 36;
  menu.style.left = (x + mw > window.innerWidth  ? x - mw : x) + 'px';
  menu.style.top  = (y + mh > window.innerHeight ? y - mh : y) + 'px';
}

function hideCtxMenu() {
  const menu = document.getElementById('ctx-menu');
  if (menu) menu.style.display = 'none';
}

document.addEventListener('click', hideCtxMenu);
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideCtxMenu(); });

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
    div.addEventListener('contextmenu', event => {
      event.preventDefault();
      setPageIdx(i);
      showCtxMenu(event.clientX, event.clientY, [
        { label: '↑ Move Up',   action: () => movePage(-1) },
        { label: '↓ Move Down', action: () => movePage(1) },
        'sep',
        { label: 'Duplicate',   action: () => dupPage() },
        'sep',
        { label: 'Delete',      action: () => delPage(), danger: true },
      ]);
    });
    wireDragRow(div, 'pages', i, (from, to) => {
      const pages = cfg.pages || [];
      if (!moveInArray(pages, from, to)) return;
      pageIdx = to;
      renderPages();
      loadPageSettings();
      renderItems();
      showNoItem();
      scheduleSave();
    });
    el.appendChild(div);
  });
}

function setPageIdx(i) {
  pageIdx = i;
  itemIdx = null;
  earnReasonIdx = null;
  earnNoteIdx = null;
  closeMobileEdit();
  renderPages();
  loadPageSettings();
  renderItems();
  showNoItem();
  if (previewSelectedOnly) reloadPreview();
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
  const removedIdx = pageIdx;
  const removedPage = JSON.parse(JSON.stringify(pages[removedIdx]));
  pages.splice(removedIdx, 1);
  const ni = Math.max(0, pageIdx - 1);
  cfg.pages = pages;
  setPageIdx(ni);
  scheduleSave();
  showUndoToast(`Deleted page "${removedPage.title || `Page ${removedIdx + 1}`}"`, () => {
    cfg.pages = cfg.pages || [];
    const restoreIdx = Math.min(removedIdx, cfg.pages.length);
    cfg.pages.splice(restoreIdx, 0, removedPage);
    setPageIdx(restoreIdx);
    scheduleSave();
  });
}

function dupPage() {
  const pages = cfg.pages || [];
  if (!pages.length) return;
  const copy = JSON.parse(JSON.stringify(pages[pageIdx]));
  copy.title = 'Copy of ' + (copy.title || `Page ${pageIdx + 1}`);
  pages.splice(pageIdx + 1, 0, copy);
  setPageIdx(pageIdx + 1);
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
  const filter = itemFilterText.trim().toLowerCase();
  (page.items || []).forEach((item, i) => {
    const searchable = itemSearchText(item);
    if (filter && !searchable.includes(filter)) return;
    const div = document.createElement('div');
    div.className = 'item-row' + (i === itemIdx ? ' selected' : '');
    div.onclick = () => selectItem(i);
    div.addEventListener('contextmenu', event => {
      event.preventDefault();
      selectItem(i);
      showCtxMenu(event.clientX, event.clientY, [
        { label: '↑ Move Up',   action: () => moveItem(-1) },
        { label: '↓ Move Down', action: () => moveItem(1) },
        'sep',
        { label: 'Duplicate',   action: () => dupItem() },
        { label: 'Copy Fields from Previous', action: () => copyPreviousItemFields() },
        'sep',
        { label: 'Delete',      action: () => delItem(), danger: true },
      ]);
    });
    wireDragRow(div, 'items', i, (from, to) => {
      const page = currentPage();
      const items = page && page.items;
      if (!moveInArray(items, from, to)) return;
      itemIdx = to;
      renderItems();
      buildItemEditor();
      scheduleSave();
    });

    const badge = document.createElement('span');
    badge.className = 'item-badge ' + (item.type === 'smilemakers' ? 'badge-sm' : 'badge-man');
    badge.textContent = item.type === 'smilemakers' ? 'SM' : 'M';

    const name = document.createElement('span');
    name.className = 'item-name';
    name.textContent = itemListLabel(item);
    div.appendChild(badge);
    div.appendChild(name);
    el.appendChild(div);
  });
}

function itemListLabel(item) {
  if (item.type === 'smilemakers') {
    const u = (item.urls || [])[0] || '?';
    const slug = u.replace(/\/$/, '').split('/').pop();
    const extra = (item.urls || []).length > 1 ? ` +${item.urls.length - 1}` : '';
    return slug + extra + (item.tag ? ` [${item.tag}]` : '');
  }
  return (item.name || '?') + (item.tag ? ` [${item.tag}]` : '');
}

function itemSearchText(item) {
  return [
    itemListLabel(item),
    item.name,
    item.desc,
    item.tag,
    item.image,
    ...(item.urls || []),
  ].filter(Boolean).join(' ').toLowerCase();
}

function filterItems(value) {
  itemFilterText = value || '';
  renderItems();
}

function selectItem(i) {
  itemIdx = i;
  renderItems();
  buildItemEditor();
  openMobileEdit();
}

function addSmItem() {
  const page = currentPage();
  if (!page) return;
  page.items = page.items || [];
  page.items.push({ type: 'smilemakers', urls: [] });
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
  const removedIdx = itemIdx;
  const removedPageIdx = pageIdx;
  const removedItem = JSON.parse(JSON.stringify(page.items[removedIdx]));
  page.items.splice(removedIdx, 1);
  itemIdx = page.items.length ? Math.max(0, removedIdx - 1) : null;
  renderItems();
  if (itemIdx === null) {
    showNoItem();
  } else {
    buildItemEditor();
  }
  scheduleSave();
  const label = removedItem.name || (removedItem.urls || [])[0] || 'item';
  showUndoToast(`Deleted ${label}`, () => {
    const targetPage = (cfg.pages || [])[removedPageIdx];
    if (!targetPage) return;
    targetPage.items = targetPage.items || [];
    const restoreIdx = Math.min(removedIdx, targetPage.items.length);
    targetPage.items.splice(restoreIdx, 0, removedItem);
    pageIdx = removedPageIdx;
    itemIdx = restoreIdx;
    renderPages();
    loadPageSettings();
    renderItems();
    buildItemEditor();
    scheduleSave();
  });
}

function dupItem() {
  const page = currentPage();
  if (!page || itemIdx === null) return;
  const copy = JSON.parse(JSON.stringify(page.items[itemIdx]));
  if (copy.name) copy.name = 'Copy of ' + copy.name;
  page.items.splice(itemIdx + 1, 0, copy);
  itemIdx = itemIdx + 1;
  renderItems();
  buildItemEditor();
  scheduleSave();
}

function copyPreviousItemFields() {
  const page = currentPage();
  if (!page || itemIdx === null || itemIdx <= 0) return;
  const items = page.items || [];
  const prev = items[itemIdx - 1];
  const item = items[itemIdx];
  if (!prev || !item) return;

  ['tag', 'variant_type', 'pickles', 'points', 'price', 'uniform_approved'].forEach(key => {
    if (prev[key] === undefined || prev[key] === null || prev[key] === '') {
      delete item[key];
    } else {
      item[key] = JSON.parse(JSON.stringify(prev[key]));
    }
  });
  if (prev.variants) {
    item.variants = JSON.parse(JSON.stringify(prev.variants));
  }
  renderItems();
  buildItemEditor();
  setStatus('Copied fields from previous item', 'ok');
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
  const titleEl = document.getElementById('mob-edit-title');
  if (titleEl) titleEl.textContent = item.name || 'Edit Item';
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
               style="width:100%;margin-top:4px;padding:4px 6px;border:1px solid var(--border);border-radius:3px;font-family:monospace;font-size:10px"
               onkeydown="if(event.key==='Enter'){event.preventDefault();urlAdd();}">
        <div class="url-actions">
          <button onclick="urlAdd()">Add</button>
          <button onclick="urlReplace()">Replace</button>
          <button onclick="urlRemove()">Remove</button>
        </div>
        <div id="fetch-status"></div>
        <div id="fetch-errors">${fetchErrorsHtml(item)}</div>
      </div>
    </div>
    <div class="ed-row">
      <label>Tag</label>
      <select id="ed-tag" onchange="itemSet('tag', this.value || null)">
        ${tags.map(t => `<option value="${t}" ${item.tag===t?'selected':''}>${t||'(none)'}</option>`).join('')}
      </select>
    </div>
    <div class="ed-row">
      <label>Uniform</label>
      <select onchange="itemSet('uniform_approved', this.value==='true'?true:this.value==='weekend'?'weekend':false)">
        <option value="false" ${!item.uniform_approved?'selected':''}>Not Approved</option>
        <option value="true" ${item.uniform_approved===true?'selected':''}>Approved</option>
        <option value="weekend" ${item.uniform_approved==='weekend'?'selected':''}>Weekends Only</option>
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
    <div class="overrides-note">Overrides &mdash; blank = auto from URL</div>
    <div class="ed-row">
      <label>Name</label>
      <div class="override-wrap">
        <input type="text" id="ed-name" value="${esc(item.name||'')}" placeholder="auto"
               oninput="itemSet('name', this.value||null)">
        ${item.name ? `<button class="clr-btn" onclick="clearOverride('name','ed-name')" title="Clear override">&times;</button>` : ''}
      </div>
    </div>
    <div class="ed-row">
      <label>Desc</label>
      <div class="override-wrap">
        <textarea id="ed-desc" placeholder="auto"
                  oninput="itemSet('desc', this.value||null)">${esc(item.desc||'')}</textarea>
        ${item.desc ? `<button class="clr-btn" onclick="clearOverride('desc','ed-desc')" title="Clear override">&times;</button>` : ''}
      </div>
    </div>
    <div class="ed-row">
      <label>Pickles</label>
      <div class="override-wrap">
        <input type="number" id="ed-pickles" min="0" placeholder="auto"
               value="${item.pickles??item.points??''}"
               oninput="itemSet('pickles', this.value?parseInt(this.value):null)">
        ${(item.pickles!=null||item.points!=null) ? `<button class="clr-btn" onclick="clearOverride('pickles','ed-pickles')" title="Clear override">&times;</button>` : ''}
      </div>
    </div>
    <div class="ed-row">
      <label>Image URL</label>
      <div class="override-wrap">
        <input type="text" id="ed-image" value="${esc(item.image||'')}" placeholder="auto"
               oninput="itemSet('image', this.value||null)">
        ${item.image ? `<button class="clr-btn" onclick="clearOverride('image','ed-image')" title="Clear override">&times;</button>` : ''}
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

function fetchErrorsHtml(item) {
  const errors = item.fetch_errors || {};
  const rows = Object.entries(errors);
  if (!rows.length) return '';
  return `
    <div class="fetch-error-list">
      ${rows.map(([url, detail]) => `
        <div class="fetch-error-row">
          <div>
            <strong>Fetch failed</strong>
            <span>${esc((url || '').replace(/\/$/, '').split('/').pop() || url)}</span>
            <small>${esc(detail.message || 'Unknown error')}</small>
          </div>
          <button onclick="retryFetchUrl(decodeURIComponent('${encodeURIComponent(url)}'))">Retry</button>
        </div>
      `).join('')}
    </div>`;
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
      <label>Uniform</label>
      <select onchange="itemSet('uniform_approved', this.value==='true'?true:this.value==='weekend'?'weekend':false)">
        <option value="false" ${!item.uniform_approved?'selected':''}>Not Approved</option>
        <option value="true" ${item.uniform_approved===true?'selected':''}>Approved</option>
        <option value="weekend" ${item.uniform_approved==='weekend'?'selected':''}>Weekends Only</option>
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
    div.addEventListener('contextmenu', event => {
      event.preventDefault();
      selectEarnReason(i);
      showCtxMenu(event.clientX, event.clientY, [
        { label: '↑ Move Up',   action: () => moveEarnReason(-1) },
        { label: '↓ Move Down', action: () => moveEarnReason(1) },
        'sep',
        { label: 'Delete',      action: () => delEarnReason(), danger: true },
      ]);
    });
    wireDragRow(div, 'earn-reasons', i, (from, to) => {
      const page = currentPage();
      if (!moveInArray(page && page.reasons, from, to)) return;
      earnReasonIdx = to;
      earnNoteIdx = null;
      renderEarnReasons();
      renderEarnNotes();
      buildEarnReasonEditor();
      scheduleSave();
    });
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
             placeholder="e.g. Whole store, Peaks only\u2026"
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
    div.addEventListener('contextmenu', event => {
      event.preventDefault();
      selectEarnNote(i);
      showCtxMenu(event.clientX, event.clientY, [
        { label: 'Delete', action: () => delEarnNote(), danger: true },
      ]);
    });
    wireDragRow(div, 'earn-notes', i, (from, to) => {
      const page = currentPage();
      if (!moveInArray(page && page.notes, from, to)) return;
      earnNoteIdx = to;
      earnReasonIdx = null;
      renderEarnReasons();
      renderEarnNotes();
      buildEarnNoteEditor();
      scheduleSave();
    });
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
  scheduleSave();
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
  scheduleSave();
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
  scheduleSave();
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
  return fetchAndApplyUrl(item, u, 'Fetching');
  const statusEl = document.getElementById('fetch-status');
  statusEl.textContent = 'Fetching\u2026';
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
async function fetchAllUrlPreviews() {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item) return;
  const urls = (item.urls || []).filter(Boolean);
  if (!urls.length) return;
  for (let i = 0; i < urls.length; i += 1) {
    await fetchAndApplyUrl(item, urls[i], `Fetching ${i + 1}/${urls.length}`);
  }
  const statusEl = document.getElementById('fetch-status');
  if (statusEl) statusEl.textContent = `Fetch complete: ${urls.length} URL${urls.length === 1 ? '' : 's'} checked`;
}

async function retryFetchUrl(url) {
  const page = currentPage();
  const item = page && itemIdx!==null ? (page.items||[])[itemIdx] : null;
  if (!item || !url) return;
  await fetchAndApplyUrl(item, url, 'Retrying');
}

async function fetchAndApplyUrl(item, u, label) {
  const statusEl = document.getElementById('fetch-status');
  if (statusEl) statusEl.textContent = `${label}: ${(u || '').replace(/\/$/, '').split('/').pop() || u}`;
  try {
    const r = await fetch('/api/fetch-product', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url: u})
    });
    const d = await r.json();
    if (d.error) {
      recordFetchError(item, u, d.error);
      if (statusEl) statusEl.textContent = 'Error: ' + d.error;
      return false;
    }
    clearFetchError(item, u);

    const nameEl    = document.getElementById('ed-name');
    const descEl    = document.getElementById('ed-desc');
    const picklesEl = document.getElementById('ed-pickles');
    const imageEl   = document.getElementById('ed-image');
    if (nameEl    && !nameEl.value)    nameEl.placeholder    = d.name  || 'auto';
    if (descEl    && !descEl.value)    descEl.placeholder    = d.desc  || 'auto';
    if (picklesEl && !picklesEl.value) picklesEl.placeholder = d.price ? `auto (~${Math.ceil(d.price / (cfg.settings?.price_per_pickle || 0.5))} pickles)` : 'auto';
    if (imageEl   && !imageEl.value)   imageEl.placeholder   = d.image || 'auto';

    const sizes = d.sizes && d.sizes.length ? `  sizes: ${d.sizes.join(', ')}` : '';
    if (statusEl) statusEl.textContent = `Fetched OK  $${d.price ? d.price.toFixed(2) : '?'}${sizes}`;
    return true;
  } catch(e) {
    recordFetchError(item, u, 'Network error');
    if (statusEl) statusEl.textContent = 'Network error';
    return false;
  }
}

function recordFetchError(item, url, message) {
  item.fetch_errors = item.fetch_errors || {};
  item.fetch_errors[url] = { message, at: new Date().toISOString() };
  refreshFetchErrors(item);
  scheduleSave();
}

function clearFetchError(item, url) {
  if (!item.fetch_errors || !item.fetch_errors[url]) return;
  delete item.fetch_errors[url];
  if (!Object.keys(item.fetch_errors).length) delete item.fetch_errors;
  refreshFetchErrors(item);
  scheduleSave();
}

function refreshFetchErrors(item) {
  const el = document.getElementById('fetch-errors');
  if (el) el.innerHTML = fetchErrorsHtml(item);
}

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
  selectedTagName = Object.keys(cfg.tag_colors || {})[0] || null;
  renderTagMgrList();
  if (selectedTagName) {
    loadTagEditor();
  }
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
  const removedTag = selectedTagName;
  const removedColors = JSON.parse(JSON.stringify(cfg.tag_colors[removedTag]));
  delete cfg.tag_colors[removedTag];
  selectedTagName = null;
  document.getElementById('tag-edit-title').textContent = 'Select a tag';
  renderTagMgrList();
  renderTagSwatches();
  scheduleSave();
  showUndoToast(`Deleted tag "${removedTag}"`, () => {
    cfg.tag_colors = cfg.tag_colors || {};
    cfg.tag_colors[removedTag] = removedColors;
    selectedTagName = removedTag;
    renderTagMgrList();
    loadTagEditor();
    renderTagSwatches();
    scheduleSave();
  });
}

// ──────────────────────────────────────────────────────────────────
// Save / Preview
// ──────────────────────────────────────────────────────────────────
async function saveConfig() {
  clearTimeout(_saveTimer);
  clearTimeout(_settingsTimer);
  _saveTimer = null;
  _settingsTimer = null;
  collectSettings();
  const validationErrors = validateSmilemakersUrls();
  if (validationErrors.length) {
    focusValidationError(validationErrors[0]);
    setStatus(validationErrors[0].message, 'err');
    return;
  }
  setStatus('Saving\u2026', 'warn');
  saveInFlight = true;
  try {
    const r = await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(cfg)
    });
    const d = await r.json();
    if (d.ok) {
      hasUnsavedChanges = false;
      setStatus('Saved ✓', 'ok');
      setTimeout(() => setStatus('Ready'), 2500);
      reloadPreview();
    } else {
      handleBackendValidationError(d.error || '?');
    }
  } catch(e) {
    setStatus('Network error', 'err');
  } finally {
    saveInFlight = false;
    markCleanIfIdle();
  }
}

function validateSmilemakersUrls() {
  const errors = [];
  const seen = new Map();
  (cfg.pages || []).forEach((page, pidx) => {
    (page.items || []).forEach((item, iidx) => {
      if (item.type !== 'smilemakers') return;
      const label = `Page ${pidx + 1}, item ${iidx + 1}`;
      const urls = item.urls || [];
      if (!urls.length) {
        errors.push({ message: `${label}: add at least one SmileMakers URL`, pageIdx: pidx, itemIdx: iidx, fieldId: 'url-entry' });
        return;
      }
      urls.forEach((raw, uidx) => {
        const url = String(raw || '').trim();
        if (!url) {
          errors.push({ message: `${label}: URL ${uidx + 1} is empty`, pageIdx: pidx, itemIdx: iidx, urlIdx: uidx, fieldId: 'url-entry' });
          return;
        }
        let parsed;
        try {
          parsed = new URL(url);
        } catch(e) {
          errors.push({ message: `${label}: URL ${uidx + 1} is not a valid URL`, pageIdx: pidx, itemIdx: iidx, urlIdx: uidx, fieldId: 'url-entry' });
          return;
        }
        if (!/^https?:$/.test(parsed.protocol) || !parsed.hostname.includes('smilemakersonline.com')) {
          errors.push({ message: `${label}: URL ${uidx + 1} must be a SmileMakers URL`, pageIdx: pidx, itemIdx: iidx, urlIdx: uidx, fieldId: 'url-entry' });
          return;
        }
        const key = parsed.href.replace(/\/$/, '').toLowerCase();
        if (seen.has(key)) {
          errors.push({ message: `${label}: duplicate URL also used at ${seen.get(key)}`, pageIdx: pidx, itemIdx: iidx, urlIdx: uidx, fieldId: 'url-entry' });
        } else {
          seen.set(key, label);
        }
      });
    });
  });
  return errors;
}

function focusValidationError(error) {
  if (!error || error.pageIdx == null) return;
  setPageIdx(error.pageIdx);
  if (error.itemIdx != null) {
    itemIdx = error.itemIdx;
    renderItems();
    buildItemEditor();
    openMobileEdit();
  }
  setTimeout(() => {
    if (error.urlIdx != null) {
      const sel = document.getElementById('url-select');
      const entry = document.getElementById('url-entry');
      if (sel && sel.options[error.urlIdx]) {
        sel.selectedIndex = error.urlIdx;
        if (entry) entry.value = sel.options[error.urlIdx].value;
      }
    }
    const field = document.getElementById(error.fieldId || '');
    if (field) {
      field.focus();
      if (typeof field.select === 'function') field.select();
    }
  }, 0);
}

function handleBackendValidationError(message) {
  const text = String(message || '?');
  setStatus('Save failed: ' + text, 'err');
  const match = text.match(/pages\[(\d+)\]\.items\[(\d+)\](?:\.urls\[(\d+)\])?/);
  if (match) {
    focusValidationError({
      message: text,
      pageIdx: parseInt(match[1], 10),
      itemIdx: parseInt(match[2], 10),
      urlIdx: match[3] == null ? null : parseInt(match[3], 10),
      fieldId: match[3] == null ? 'ed-name' : 'url-entry',
    });
    return;
  }
  const pageMatch = text.match(/pages\[(\d+)\]/);
  if (pageMatch) {
    setPageIdx(parseInt(pageMatch[1], 10));
  }
}

// Auto-save: debounce 700ms after any change, then save + refresh preview.
let _saveTimer = null;
function scheduleSave() {
  clearTimeout(_saveTimer);
  markDirty();
  setStatus('Unsaved changes\u2026', 'warn');
  _saveTimer = setTimeout(() => saveConfig(), 700);
}

// Settings-only save: update cfg immediately, debounce the disk write, no preview reload.
let _settingsTimer = null;
async function scheduleSettingsSave() {
  collectSettings();   // update cfg in memory RIGHT NOW so switching items never loses data
  clearTimeout(_settingsTimer);
  markDirty();
  setStatus('Unsaved changes\u2026', 'warn');
  _settingsTimer = setTimeout(async () => {
    _settingsTimer = null;
    collectSettings(); // re-collect at write time in case of rapid changes
    setStatus('Saving\u2026', 'warn');
    saveInFlight = true;
    try {
      const r = await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(cfg)
      });
      const d = await r.json();
      if (d.ok) {
        hasUnsavedChanges = false;
        setStatus('Saved ✓', 'ok');
        setTimeout(() => setStatus('Ready'), 2500);
      } else {
        handleBackendValidationError(d.error || '?');
      }
    } catch(e) {
      setStatus('Network error', 'err');
    } finally {
      saveInFlight = false;
      markCleanIfIdle();
    }
  }, 900);
}

function reloadPreview() {
  const f = document.getElementById('preview-frame');
  const s = document.getElementById('preview-status');
  const previousScroll = getPreviewScroll(f);
  if (s) s.textContent = 'Refreshing\u2026';
  f.addEventListener('load', () => {
    restorePreviewScroll(f, previousScroll);
  }, { once: true });
  f.src = previewUrl('/preview-frame');
  f.onload = () => { if (s) s.textContent = previewSelectedOnly ? 'Selected page preview' : 'Live preview'; };
}

function openPreview() {
  window.open(previewUrl('/preview'), '_blank');
}

function openOrderTracker() {
  window.open(previewUrl('/order-tracker'), '_blank');
}

function previewUrl(base) {
  const params = new URLSearchParams({ t: Date.now().toString() });
  if (previewSelectedOnly) params.set('page', String(pageIdx));
  return `${base}?${params.toString()}`;
}

function toggleSelectedPreview() {
  previewSelectedOnly = !previewSelectedOnly;
  updatePreviewModeButton();
  reloadPreview();
}

function updatePreviewModeButton() {
  const btn = document.getElementById('btn-preview-selected');
  if (!btn) return;
  btn.classList.toggle('active', previewSelectedOnly);
  btn.textContent = previewSelectedOnly ? 'Selected Page' : 'All Pages';
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
  const frame = document.getElementById('preview-frame');
  handle.addEventListener('mousedown', e => {
    startX  = e.clientX;
    startRW = right.offsetWidth;
    startPW = prev.offsetWidth;
    handle.classList.add('dragging');
    if (frame) frame.style.pointerEvents = 'none';
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
    if (frame) frame.style.pointerEvents = '';
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

// ──────────────────────────────────────────────────────────────────
// Mobile panel switching
// ──────────────────────────────────────────────────────────────────

// right-panel is a slide-in overlay, not a regular panel tab
const PANEL_IDS = ['left-panel', 'center-panel', 'preview-panel'];

function showMobilePanel(panel, btn) {
  const map = { left: 'left-panel', center: 'center-panel', preview: 'preview-panel' };
  const targetId = map[panel];
  PANEL_IDS.forEach(id => {
    document.getElementById(id).classList.toggle('mob-hidden', id !== targetId);
  });
  document.querySelectorAll('.mob-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  if (panel === 'preview') reloadPreview();
}

function openMobileEdit() {
  if (window.innerWidth > 900) return;
  // Update title with item name
  const page = currentPage();
  const item = page && itemIdx != null ? (page.items || [])[itemIdx] : null;
  const titleEl = document.getElementById('mob-edit-title');
  if (titleEl) titleEl.textContent = item?.name || 'Edit Item';
  document.getElementById('right-panel').classList.add('mob-edit-open');
}

function closeMobileEdit() {
  document.getElementById('right-panel').classList.remove('mob-edit-open');
  // Return to center (Page/Items) panel
  if (window.innerWidth <= 900) {
    const centerBtn = document.querySelector('.mob-btn:nth-child(2)');
    showMobilePanel('center', centerBtn);
  }
}

function initMobile() {
  const isMobile = window.innerWidth <= 900;
  if (!isMobile) {
    // Desktop: unhide all panels and clear any drag-set explicit widths
    PANEL_IDS.forEach(id => document.getElementById(id).classList.remove('mob-hidden'));
    document.getElementById('right-panel').classList.remove('mob-edit-open');
    const right = document.getElementById('right-panel');
    const prev  = document.getElementById('preview-panel');
    right.style.flex = '';
    right.style.width = '';
    prev.style.flex = '';
    prev.style.width = '';
    return;
  }
  // Mobile: close edit overlay; ensure exactly one main panel is visible
  closeMobileEdit();
  const visible = PANEL_IDS.filter(id => !document.getElementById(id).classList.contains('mob-hidden'));
  if (visible.length !== 1) {
    PANEL_IDS.forEach(id => {
      document.getElementById(id).classList.toggle('mob-hidden', id !== 'left-panel');
    });
    document.querySelectorAll('.mob-btn').forEach((b, i) => b.classList.toggle('active', i === 0));
  }
}

window.addEventListener('resize', initMobile);

// Boot
wireUnsavedNavigationGuard();
boot().then(() => initMobile());
