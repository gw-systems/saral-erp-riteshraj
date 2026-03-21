(() => {
  const cfg = window.courierWorkspaceConfig;
  if (!cfg) return;

  const s = {
    wh: [],
    orderType: cfg.initialOrderType || 'b2c',
    orderStatus: cfg.initialOrderStatus || 'all',
    orderSearch: '',
    orders: [],
    selOrders: new Set(),
    ftlStatus: 'all',
    ftlOrders: [],
    selFtl: new Set(),
    shipType: cfg.initialShipmentType || 'b2c',
    shipSearch: '',
    shipOrders: [],
    selShip: new Set(),
    shipCompare: [],
    shipCarrier: null,
    shipCompareToken: 0,
    shipWh: null,
    shipFtl: [],
    selShipFtl: new Set(),
  };

  const q = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
  const intOrNull = (v) => {
    const n = parseInt(v, 10);
    return Number.isInteger(n) ? n : null;
  };
  const money = (v) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(num(v));
  const join = (a, b) => `${String(a).replace(/\/+$/, '')}/${String(b).replace(/^\/+/, '')}`;
  const withId = (u, id) => String(u).replace('999999', String(id)).replace(/\/1(?=\/|$)/, `/${id}`);
  const csrf = () => ((document.cookie.split(';').map((x) => x.trim()).find((x) => x.startsWith('csrftoken=')) || '').split('=').slice(1).join('='));
  const SHIP_SELECTION_KEY = 'courier.shipSelection';
  const orderTypeOf = (o) => {
    const ct = String(o?.carrier_type || '').toLowerCase();
    return ct === 'b2b' || ct === 'b2c' ? ct : (num(o?.applicable_weight ?? o?.weight) >= 20 ? 'b2b' : 'b2c');
  };
  const badge = (st) => ({
    draft: 'bg-amber-100 text-amber-700',
    booked: 'bg-blue-100 text-blue-700',
    manifested: 'bg-cyan-100 text-cyan-700',
    picked_up: 'bg-indigo-100 text-indigo-700',
    out_for_delivery: 'bg-indigo-100 text-indigo-700',
    delivered: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-red-100 text-red-700',
    pickup_exception: 'bg-orange-100 text-orange-700',
    ndr: 'bg-orange-100 text-orange-700',
    rto: 'bg-slate-200 text-slate-700',
  })[String(st || '').toLowerCase()] || 'bg-gray-100 text-gray-700';

  function toast(msg, type = 'info') {
    const c = q('courier-toast-container');
    if (!c) return;
    const n = document.createElement('div');
    n.className = `pointer-events-auto rounded-2xl px-4 py-3 text-sm shadow-2xl text-white ${
      type === 'success' ? 'bg-emerald-600' :
      type === 'error' ? 'bg-red-600' :
      type === 'warning' ? 'bg-amber-500' :
      'bg-slate-900'
    }`;
    n.textContent = msg;
    c.appendChild(n);
    setTimeout(() => n.remove(), 4200);
  }

  function formatError(data, status) {
    if (!data) return `Request failed (${status})`;
    if (typeof data.detail === 'string' && data.detail.trim()) return data.detail;
    const parts = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : (typeof v === 'string' ? v : JSON.stringify(v))}`).filter(Boolean);
    return parts.length ? parts.join(' | ') : `Request failed (${status})`;
  }

  async function api(url, opts = {}) {
    const h = new Headers(opts.headers || {});
    h.set('Accept', 'application/json');
    if (opts.body && !(opts.body instanceof FormData)) {
      h.set('Content-Type', 'application/json');
      opts.body = JSON.stringify(opts.body);
    }
    if ((opts.method || 'GET').toUpperCase() !== 'GET') h.set('X-CSRFToken', csrf());
    const r = await fetch(url, { ...opts, headers: h });
    const t = await r.text();
    let d = {};
    try { d = t ? JSON.parse(t) : {}; } catch { d = { detail: t }; }
    if (!r.ok) throw new Error(formatError(d, r.status));
    return d;
  }

  async function blob(url, opts = {}) {
    const h = new Headers(opts.headers || {});
    if (opts.body) {
      h.set('Content-Type', 'application/json');
      opts.body = JSON.stringify(opts.body);
    }
    if ((opts.method || 'GET').toUpperCase() !== 'GET') h.set('X-CSRFToken', csrf());
    const r = await fetch(url, { ...opts, headers: h });
    if (!r.ok) throw new Error(await r.text() || 'Download failed');
    return await r.blob();
  }

  function download(file, name) {
    const u = URL.createObjectURL(file);
    const a = document.createElement('a');
    a.href = u;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 500);
  }

  function modal(id, open) {
    const m = q(id);
    if (!m) return;
    m.classList.toggle('hidden', !open);
    document.body.classList.toggle('overflow-hidden', open);
  }

  function closeModals() {
    document.querySelectorAll('.courier-modal').forEach((m) => m.classList.add('hidden'));
    document.body.classList.remove('overflow-hidden');
  }

  function arr(data) {
    return Array.isArray(data) ? data : (Array.isArray(data?.results) ? data.results : []);
  }

  function active(btns, fn) {
    btns.forEach((b) => b.classList.toggle('is-active', fn(b)));
  }

  function markSelectAll(el, ids, selected) {
    if (!el) return;
    const total = ids.length;
    const picked = ids.filter((id) => selected.has(id)).length;
    el.checked = total > 0 && picked === total;
    el.indeterminate = picked > 0 && picked < total;
  }

  function parseFlash() {
    const p = new URLSearchParams(window.location.search);
    const flash = p.get('flash');
    if (!flash) return;
    if (flash === 'created') toast('Draft saved successfully.', 'success');
    if (flash === 'updated') toast('Draft updated successfully.', 'success');
    p.delete('flash');
    const next = `${window.location.pathname}${p.toString() ? `?${p}` : ''}${window.location.hash || ''}`;
    window.history.replaceState({}, '', next);
  }

  function whLinked(w) {
    return !!(w?.shipdaak_pickup_id && w?.shipdaak_rto_id);
  }

  function whOptions() {
    return s.wh.filter((w) => w.is_active !== false).map((w) => `<option value="${w.id}">${esc(w.name)} (${esc(w.pincode)})</option>`).join('');
  }

  function fillWhSelects() {
    const ship = q('courier-shipment-warehouse');
    if (!ship) return;
    ship.innerHTML = `<option value="">Use sender pincode from order</option>${whOptions()}`;
    if (s.shipWh) ship.value = String(s.shipWh);
  }

  async function loadWh() {
    s.wh = arr(await api(cfg.warehouseListUrl));
    fillWhSelects();
    if (cfg.activeSection === 'warehouses') renderWh();
  }

  function renderWh() {
    const el = q('courier-warehouse-list');
    if (!el) return;
    if (!s.wh.length) {
      el.innerHTML = '<div class="courier-surface p-6 text-sm text-gray-500">No courier warehouses yet.</div>';
      return;
    }
    el.innerHTML = s.wh.map((w) => `<article class="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"><div class="min-w-0 flex-1"><div class="flex items-center gap-3"><h3 class="text-lg font-semibold text-gray-900">${esc(w.name)}</h3><span class="rounded-full px-3 py-1 text-xs font-semibold ${whLinked(w) ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}">${whLinked(w) ? 'Linked to ShipDaak' : 'Not Linked to ShipDaak'}</span></div><p class="mt-2 text-sm text-gray-600">${esc(w.address)}${w.address_2 ? `, ${esc(w.address_2)}` : ''}</p><p class="mt-1 text-sm text-gray-600">${esc(w.city)}, ${esc(w.state)} · ${esc(w.pincode)}</p><p class="mt-1 text-sm text-gray-600">Contact: ${esc(w.contact_name)} (${esc(w.contact_no)})</p><p class="mt-3 text-xs text-gray-500">Pickup ID: ${esc(w.shipdaak_pickup_id || '-')} · RTO ID: ${esc(w.shipdaak_rto_id || '-')}</p></div><div class="flex flex-wrap gap-2 lg:max-w-xs lg:justify-end"><button type="button" data-wh-sync="${w.id}" class="${whLinked(w) ? 'cursor-not-allowed rounded-xl bg-slate-300 px-4 py-2 text-sm font-semibold text-white' : 'rounded-xl bg-orange-600 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-700'}" ${whLinked(w) ? 'disabled' : ''}>${whLinked(w) ? 'Already Linked' : 'Create New In ShipDaak'}</button><button type="button" data-wh-link="${w.id}" class="rounded-xl border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Link Existing ShipDaak IDs</button></div></div></article>`).join('');
  }

  async function loadOrders() {
    const url = s.orderStatus === 'all' ? cfg.orderListUrl : `${cfg.orderListUrl}?status=${encodeURIComponent(s.orderStatus)}`;
    s.orders = arr(await api(url));
    renderOrders();
  }

  function orderRows() {
    let rows = s.orders.filter((o) => orderTypeOf(o) === s.orderType);
    if (s.orderSearch) {
      const n = s.orderSearch.toLowerCase();
      rows = rows.filter((o) => [o.order_number, o.recipient_name, o.recipient_pincode, o.selected_carrier, o.awb_number, o.warehouse_name].join(' ').toLowerCase().includes(n));
    }
    return rows;
  }

  function updateCreateLink() {
    const btn = q('courier-open-create-order');
    if (!btn) return;
    if (s.orderType === 'ftl') {
      btn.textContent = 'Create FTL Order';
      btn.href = cfg.ftlCreateUrl;
      return;
    }
    if (s.orderType === 'b2b') {
      btn.textContent = 'Create B2B Order';
      btn.href = cfg.orderCreateB2bUrl;
      return;
    }
    btn.textContent = 'Create B2C Order';
    btn.href = cfg.orderCreateB2cUrl;
  }

  function syncOrderPanes() {
    q('courier-orders-status-toolbar')?.classList.toggle('hidden', s.orderType === 'ftl');
    q('courier-orders-regular-pane')?.classList.toggle('hidden', s.orderType === 'ftl');
    q('courier-orders-ftl-pane')?.classList.toggle('hidden', s.orderType !== 'ftl');
  }

  function syncShipmentPanes() {
    const isFtl = s.shipType === 'ftl';
    q('courier-shipments-regular-pane')?.classList.toggle('hidden', isFtl);
    q('courier-shipments-ftl-pane')?.classList.toggle('hidden', !isFtl);
  }

  function paintControls() {
    active(document.querySelectorAll('[data-orders-type]'), (b) => b.dataset.ordersType === s.orderType);
    active(document.querySelectorAll('[data-orders-status]'), (b) => b.dataset.ordersStatus === s.orderStatus);
    active(document.querySelectorAll('[data-ftl-status]'), (b) => b.dataset.ftlStatus === s.ftlStatus);
    active(document.querySelectorAll('[data-shipment-type]'), (b) => b.dataset.shipmentType === s.shipType);
  }

  function updateOrderActions() {
    const bar = q('courier-orders-actions');
    if (!bar) return;
    const rows = s.orders.filter((o) => s.selOrders.has(o.id));
    const count = rows.length;
    bar.classList.toggle('hidden', count === 0 || s.orderType === 'ftl');
    q('courier-orders-selected-count').textContent = `${count} selected`;
    const allDraft = count > 0 && rows.every((o) => o.status === 'draft');
    const allBooked = count > 0 && rows.every((o) => o.status === 'booked');
    const anyAwb = rows.some((o) => o.awb_number);
    q('courier-order-edit-action').classList.toggle('hidden', !(count === 1 && allDraft));
    q('courier-order-book-awb-action').classList.toggle('hidden', !allDraft);
    q('courier-order-manifest-action').classList.toggle('hidden', !rows.some((o) => ['booked', 'manifested'].includes(o.status) && o.awb_number));
    q('courier-order-cancel-action').classList.toggle('hidden', !allBooked);
    q('courier-order-label-action').classList.toggle('hidden', !anyAwb);
    q('courier-order-details-action').classList.toggle('hidden', count !== 1);
    q('courier-order-track-action').classList.toggle('hidden', !(count === 1 && anyAwb));
    q('courier-order-sync-action').classList.toggle('hidden', !anyAwb);
  }

  function renderOrders() {
    const el = q('courier-orders-list');
    if (!el) return;
    paintControls();
    syncOrderPanes();
    updateCreateLink();
    const rows = orderRows();
    if (!rows.length) {
      el.innerHTML = '<tr><td colspan="9" class="courier-table-empty">No orders matched this filter.</td></tr>';
      markSelectAll(q('courier-orders-select-all'), [], s.selOrders);
      updateOrderActions();
      return;
    }
    el.innerHTML = rows.map((o) => `<tr><td class="courier-table-check"><input type="checkbox" class="order-box" value="${o.id}" ${s.selOrders.has(o.id) ? 'checked' : ''}></td><td><span class="courier-table-title-cell">${esc(o.order_number)}</span><span class="courier-table-subtext">${esc(o.created_at ? new Date(o.created_at).toLocaleString('en-IN') : 'Draft')}</span></td><td><span class="courier-table-title-cell">${esc(o.recipient_name)}</span><span class="courier-table-subtext">${esc(o.recipient_pincode)}</span></td><td>${esc(o.applicable_weight ?? o.weight ?? '-')} kg</td><td>${esc(String(o.payment_mode || '-').toUpperCase())}</td><td>${esc(o.warehouse_name || o.courier_warehouse_name || '-')}</td><td>${esc(o.selected_carrier || '-')}</td><td>${esc(o.awb_number || '-')}</td><td><span class="courier-status-pill ${badge(o.status)}">${esc(String(o.status || '-').replace(/_/g, ' ').toUpperCase())}</span></td></tr>`).join('');
    markSelectAll(q('courier-orders-select-all'), rows.map((r) => r.id), s.selOrders);
    updateOrderActions();
  }

  async function loadFtlOrders() {
    const url = s.ftlStatus === 'all' ? cfg.ftlOrderListUrl : `${cfg.ftlOrderListUrl}?status=${encodeURIComponent(s.ftlStatus)}`;
    s.ftlOrders = arr(await api(url));
    renderFtlOrders();
  }

  function ftlRows() {
    let rows = s.ftlOrders;
    if (s.ftlStatus !== 'all') rows = rows.filter((o) => o.status === s.ftlStatus);
    if (s.orderSearch) {
      const n = s.orderSearch.toLowerCase();
      rows = rows.filter((o) => [o.order_number, o.name, o.phone, o.source_city, o.destination_city, o.container_type].join(' ').toLowerCase().includes(n));
    }
    return rows;
  }

  function updateFtlActions() {
    const bar = q('courier-ftl-orders-actions');
    if (!bar) return;
    const rows = s.ftlOrders.filter((o) => s.selFtl.has(o.id));
    bar.classList.toggle('hidden', rows.length === 0 || s.orderType !== 'ftl');
    q('courier-ftl-orders-selected-count').textContent = `${rows.length} selected`;
    q('courier-ftl-edit-action').classList.toggle('hidden', !(rows.length === 1 && rows[0].status === 'draft'));
    q('courier-ftl-cancel-action').classList.toggle('hidden', !(rows.length > 0 && rows.every((o) => o.status === 'booked')));
  }

  function renderFtlOrders() {
    const el = q('courier-ftl-orders-list');
    if (!el) return;
    paintControls();
    syncOrderPanes();
    updateCreateLink();
    const rows = ftlRows();
    if (!rows.length) {
      el.innerHTML = '<tr><td colspan="8" class="courier-table-empty">No FTL orders matched this filter.</td></tr>';
      markSelectAll(q('courier-ftl-orders-select-all'), [], s.selFtl);
      updateFtlActions();
      return;
    }
    el.innerHTML = rows.map((o) => `<tr><td class="courier-table-check"><input type="checkbox" class="ftl-box" value="${o.id}" ${s.selFtl.has(o.id) ? 'checked' : ''}></td><td><span class="courier-table-title-cell">${esc(o.order_number)}</span></td><td><span class="courier-table-title-cell">${esc(o.name)}</span><span class="courier-table-subtext">${esc(o.phone)}</span></td><td>${esc(o.source_city)} to ${esc(o.destination_city)}</td><td>${esc(o.container_type)}</td><td>${money(o.base_price)}</td><td>${money(o.total_price)}</td><td><span class="courier-status-pill ${badge(o.status)}">${esc(String(o.status || '-').replace(/_/g, ' ').toUpperCase())}</span></td></tr>`).join('');
    markSelectAll(q('courier-ftl-orders-select-all'), rows.map((r) => r.id), s.selFtl);
    updateFtlActions();
  }

  async function loadShipOrders() {
    s.shipOrders = arr(await api(`${cfg.orderListUrl}?status=draft`)).filter((o) => orderTypeOf(o) === s.shipType);
    renderShipOrders();
    consumeShipSelection();
  }

  function shipRows() {
    let rows = s.shipOrders;
    if (s.shipSearch) {
      const n = s.shipSearch.toLowerCase();
      rows = rows.filter((o) => [o.order_number, o.recipient_name, o.recipient_pincode, o.awb_number, o.warehouse_name].join(' ').toLowerCase().includes(n));
    }
    return rows;
  }

  function renderCompare() {
    const el = q('courier-shipment-comparison');
    if (!el) return;
    q('courier-shipment-selection-count').textContent = `${s.selShip.size} selected`;
    if (!s.selShip.size) {
      el.innerHTML = '<div class="courier-ftl-placeholder">Select one or more draft orders to compare carrier options.</div>';
      return;
    }
    if (!s.shipCompare.length) {
      el.innerHTML = '<div class="courier-ftl-placeholder">Carrier options will appear here after the selected order set is compared.</div>';
      return;
    }
    el.innerHTML = `${s.shipCompare.map((c, i) => `<label class="courier-compare-card ${s.shipCarrier === i ? 'is-selected' : ''}"><div class="courier-compare-card-head"><input type="radio" name="ship-carrier" class="ship-carrier-radio mt-1 h-4 w-4 border-gray-300 text-blue-600" value="${i}" ${s.shipCarrier === i ? 'checked' : ''}><div class="min-w-0 flex-1"><div class="flex items-start justify-between gap-3"><div><p class="courier-table-title-cell">${esc(c.carrier || c.carrier_name || 'Carrier')}</p><p class="courier-compare-card-copy">${esc(c.mode || '-')} · ${esc(c.applied_zone || c.zone || '-')} · ${esc(c.service_category || 'Forward')}</p></div><div class="courier-compare-cost">${money(c.total_cost)}</div></div></div></div></label>`).join('')}<div class="courier-compare-footer"><p class="courier-compare-footer-copy">Booking preserves the full aggregator and service identity shown on the selected carrier card.</p><button type="button" id="courier-book-selected-carrier" class="courier-primary-link">Book Selected Carrier</button></div>`;
  }

  function renderShipOrders() {
    const el = q('courier-shipment-orders-list');
    if (!el) return;
    paintControls();
    syncShipmentPanes();
    q('courier-shipments-heading').textContent = `Select ${s.shipType.toUpperCase()} Orders To Ship`;
    q('courier-shipment-selection-count').textContent = `${s.selShip.size} selected`;
    const rows = shipRows();
    if (!rows.length) {
      el.innerHTML = '<tr><td colspan="7" class="courier-table-empty">No draft orders are available for this shipment type.</td></tr>';
      markSelectAll(q('courier-shipments-select-all'), [], s.selShip);
      renderCompare();
      return;
    }
    el.innerHTML = rows.map((o) => `<tr><td class="courier-table-check"><input type="checkbox" class="ship-box" value="${o.id}" ${s.selShip.has(o.id) ? 'checked' : ''}></td><td><span class="courier-table-title-cell">${esc(o.order_number)}</span><span class="courier-table-subtext">${esc(o.created_at ? new Date(o.created_at).toLocaleString('en-IN') : 'Draft')}</span></td><td><span class="courier-table-title-cell">${esc(o.recipient_name)}</span><span class="courier-table-subtext">${esc(o.recipient_pincode)}</span></td><td>${esc(o.applicable_weight ?? o.weight ?? '-')} kg</td><td>${esc(String(o.payment_mode || '-').toUpperCase())}</td><td>${esc(o.warehouse_name || o.courier_warehouse_name || '-')}</td><td>${esc(o.awb_number || '-')}</td></tr>`).join('');
    markSelectAll(q('courier-shipments-select-all'), rows.map((r) => r.id), s.selShip);
    renderCompare();
  }

  async function compareCarriers() {
    const token = ++s.shipCompareToken;
    if (!s.selShip.size) {
      s.shipCompare = [];
      s.shipCarrier = null;
      renderCompare();
      return;
    }
    try {
      const body = { order_ids: Array.from(s.selShip), business_type: s.shipType };
      if (s.shipWh) body.warehouse_id = s.shipWh;
      const r = await api(cfg.compareCarriersUrl, { method: 'POST', body });
      if (token !== s.shipCompareToken) return;
      s.shipCompare = arr(r.carriers || []).filter((c) => String(c.service_category || '').toLowerCase() !== 'rvp');
      s.shipCarrier = null;
      renderCompare();
    } catch (e) {
      if (token !== s.shipCompareToken) return;
      s.shipCompare = [];
      s.shipCarrier = null;
      renderCompare();
      toast(e.message, 'error');
    }
  }

  async function loadShipFtl() {
    s.shipFtl = arr(await api(`${cfg.ftlOrderListUrl}?status=draft`));
    renderShipFtl();
    consumeShipSelection();
  }

  function renderShipFtl() {
    const el = q('courier-shipments-ftl-list');
    if (!el) return;
    paintControls();
    syncShipmentPanes();
    const bar = q('courier-shipments-ftl-actions');
    if (!s.shipFtl.length) {
      if (bar) bar.classList.add('hidden');
      el.innerHTML = '<tr><td colspan="6" class="courier-table-empty">No draft FTL orders are waiting for booking.</td></tr>';
      markSelectAll(q('courier-shipments-ftl-select-all'), [], s.selShipFtl);
      return;
    }
    if (bar) bar.classList.toggle('hidden', s.selShipFtl.size === 0 || s.shipType !== 'ftl');
    q('courier-shipments-ftl-selected-count').textContent = `${s.selShipFtl.size} selected`;
    el.innerHTML = s.shipFtl.map((o) => `<tr><td class="courier-table-check"><input type="checkbox" class="ship-ftl-box" value="${o.id}" ${s.selShipFtl.has(o.id) ? 'checked' : ''}></td><td><span class="courier-table-title-cell">${esc(o.order_number)}</span></td><td>${esc(o.source_city)} to ${esc(o.destination_city)}</td><td>${esc(o.container_type)}</td><td>${money(o.total_price)}</td><td><span class="courier-status-pill ${badge(o.status)}">${esc(String(o.status || '-').replace(/_/g, ' ').toUpperCase())}</span></td></tr>`).join('');
    markSelectAll(q('courier-shipments-ftl-select-all'), s.shipFtl.map((o) => o.id), s.selShipFtl);
  }

  async function cancelOrders() {
    const ids = Array.from(s.selOrders);
    if (!ids.length || !confirm(`Cancel booking for ${ids.length} order(s)?`)) return;
    for (const id of ids) await api(join(cfg.orderListUrl, `${id}/cancel/`), { method: 'POST', body: {} });
    toast('Booking cancelled.', 'success');
    s.selOrders.clear();
    await loadOrders();
  }

  async function cancelFtl() {
    const ids = Array.from(s.selFtl);
    if (!ids.length || !confirm(`Cancel ${ids.length} FTL booking(s)?`)) return;
    for (const id of ids) await api(join(cfg.ftlOrderListUrl, `${id}/cancel/`), { method: 'POST', body: {} });
    toast('FTL bookings cancelled.', 'success');
    s.selFtl.clear();
    await loadFtlOrders();
  }

  async function delOrders() {
    const ids = Array.from(s.selOrders);
    if (!ids.length || !confirm(`Delete ${ids.length} order(s)?`)) return;
    for (const id of ids) await api(join(cfg.orderListUrl, `${id}/`), { method: 'DELETE' });
    s.selOrders.clear();
    toast('Orders deleted.', 'success');
    await loadOrders();
  }

  async function delFtl() {
    const ids = Array.from(s.selFtl);
    if (!ids.length || !confirm(`Delete ${ids.length} FTL order(s)?`)) return;
    for (const id of ids) await api(join(cfg.ftlOrderListUrl, `${id}/`), { method: 'DELETE' });
    s.selFtl.clear();
    toast('FTL orders deleted.', 'success');
    await loadFtlOrders();
  }

  async function syncStatuses() {
    const ids = Array.from(s.selOrders);
    if (!ids.length) return;
    await api(join(cfg.orderListUrl, 'shipdaak/sync-statuses/'), { method: 'POST', body: { order_ids: ids } });
    toast('Statuses synced.', 'success');
    await loadOrders();
  }

  async function orderDetails() {
    const id = Array.from(s.selOrders)[0];
    if (!id) return;
    const o = await api(join(cfg.orderListUrl, `${id}/`));
    q('courier-order-details-subtitle').textContent = o.order_number || '-';
    q('courier-order-details-content').innerHTML = [['Recipient', o.recipient_name], ['Contact', o.recipient_contact], ['Status', o.status], ['Warehouse', o.warehouse_name || o.courier_warehouse_name], ['AWB', o.awb_number], ['Carrier', o.selected_carrier || o.carrier], ['Weight', o.applicable_weight ?? o.weight], ['Payment', o.payment_mode], ['Order Value', o.order_value], ['Total Cost', o.total_cost], ['Zone', o.zone_applied], ['Mode', o.mode]].map(([k, v]) => `<div class="rounded-2xl border border-gray-200 bg-gray-50 p-4"><p class="text-xs font-semibold uppercase tracking-wide text-gray-500">${esc(k)}</p><p class="mt-2 text-sm font-medium text-gray-900 break-words">${esc(v == null || v === '' ? '-' : v)}</p></div>`).join('');
    modal('courier-order-details-modal', true);
  }

  async function tracking() {
    const id = Array.from(s.selOrders)[0];
    if (!id) return;
    const o = await api(join(cfg.orderListUrl, `${id}/`));
    const p = await api(withId(cfg.shipmentTrackBaseUrl, id));
    const list = [p?.shipment_track_activities, p?.tracking, p?.tracking_data, p?.data?.tracking, p?.data?.tracking_data, p?.activities].find((x) => Array.isArray(x) && x.length) || [];
    q('courier-tracking-subtitle').textContent = `${o.order_number} · ${o.awb_number || 'No AWB'}`;
    q('courier-tracking-content').innerHTML = list.length ? list.map((x, i) => `<div class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold text-gray-900">${esc(x.status || x.activity || x.description || `Event ${i + 1}`)}</p><p class="mt-1 text-sm text-gray-600">${esc(x.message || x.description || x.location || x.event || '-')}</p></div><span class="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">${esc(x.date || x.datetime || x.created_at || x.time || '-')}</span></div></div>`).join('') : `<div class="rounded-2xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600"><pre class="overflow-x-auto whitespace-pre-wrap text-xs">${esc(JSON.stringify(p, null, 2))}</pre></div>`;
    modal('courier-tracking-modal', true);
  }

  async function invoices() {
    const ids = Array.from(s.selOrders);
    if (!ids.length) return;
    if (ids.length === 1) {
      download(await blob(withId(cfg.singleInvoiceBaseUrl, ids[0])), 'courier-invoice.pdf');
      return;
    }
    download(await blob(cfg.multiInvoiceUrl, { method: 'POST', body: { order_ids: ids } }), 'courier-invoices.zip');
  }

  function selectedOrders() {
    return s.orders.filter((o) => s.selOrders.has(o.id));
  }

  async function labels() {
    const awbs = selectedOrders().map((o) => o.awb_number).filter(Boolean);
    if (!awbs.length) return toast('Selected orders do not have AWBs.', 'warning');
    const r = await api(cfg.bulkLabelUrl, { method: 'POST', body: { awb_numbers: [...new Set(awbs)] } });
    if (r.label_url) window.open(r.label_url, '_blank', 'noopener,noreferrer');
    toast('Label request sent.', 'success');
  }

  async function manifest() {
    const awbs = selectedOrders().filter((o) => ['booked', 'manifested'].includes(o.status) && o.awb_number).map((o) => o.awb_number);
    if (!awbs.length) return toast('Select booked or manifested orders with AWBs.', 'warning');
    const r = await api(cfg.manifestUrl, { method: 'POST', body: { awb_numbers: [...new Set(awbs)] } });
    const u = r.manifest_url || r.url || r.manifest;
    if (u) window.open(u, '_blank', 'noopener,noreferrer');
    toast('Manifest generated.', 'success');
  }

  async function startShipBooking() {
    if (cfg.activeSection === 'orders') {
      const ids = Array.from(s.selOrders);
      if (!ids.length) {
        toast('Select at least one draft order to book.', 'warning');
        return;
      }
      try {
        window.sessionStorage.setItem(SHIP_SELECTION_KEY, JSON.stringify({ type: s.orderType, ids }));
      } catch (_) {
        // Ignore storage errors and still route to the shipment workbench.
      }
      window.location.href = `${cfg.shipmentsDashboardUrl}?type=${encodeURIComponent(s.orderType)}`;
      return;
    }
    if (s.shipType === 'ftl') return;
    s.shipCompareToken += 1;
    s.shipCompare = [];
    s.shipCarrier = null;
    renderCompare();
    await compareCarriers();
  }

  function consumeShipSelection() {
    try {
      const raw = window.sessionStorage.getItem(SHIP_SELECTION_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.type === s.shipType && Array.isArray(parsed.ids)) {
          parsed.ids.map(intOrNull).forEach((id) => {
            if (Number.isInteger(id)) s.selShip.add(id);
          });
        }
        window.sessionStorage.removeItem(SHIP_SELECTION_KEY);
      }
    } catch (_) {
      // Ignore invalid session state and continue with current in-memory selection.
    }

    const shipIds = new Set(s.shipOrders.map((o) => o.id));
    Array.from(s.selShip).forEach((id) => {
      if (!shipIds.has(id)) s.selShip.delete(id);
    });

    const shipFtlIds = new Set(s.shipFtl.map((o) => o.id));
    Array.from(s.selShipFtl).forEach((id) => {
      if (!shipFtlIds.has(id)) s.selShipFtl.delete(id);
    });

    const isFtl = s.shipType === 'ftl';
    syncShipmentPanes();

    if (isFtl) {
      s.selShip.clear();
      s.shipCompareToken += 1;
      s.shipCompare = [];
      s.shipCarrier = null;
      renderShipFtl();
      renderCompare();
      return;
    }

    s.selShipFtl.clear();
    renderShipFtl();
    renderShipOrders();
    if (s.selShip.size) {
      void startShipBooking();
      return;
    }
    s.shipCompareToken += 1;
    s.shipCompare = [];
    s.shipCarrier = null;
    renderCompare();
  }

  async function bookCarrier() {
    const selected = s.shipCompare[s.shipCarrier];
    if (!selected) {
      toast('Select a carrier card before booking.', 'warning');
      return;
    }
    const body = {
      order_ids: Array.from(s.selShip),
      business_type: s.shipType,
      use_global_account: !!q('courier-use-global-account')?.checked,
    };
    if (selected.carrier_id != null) {
      body.carrier_id = selected.carrier_id;
    } else {
      body.carrier_name = selected.carrier || selected.carrier_name || '';
      body.mode = selected.mode || 'Surface';
    }
    if (s.shipWh) body.warehouse_id = s.shipWh;
    const r = await api(cfg.bookCarrierUrl, { method: 'POST', body });
    toast(r.message || 'Carrier booked successfully.', 'success');
    s.selShip.clear();
    s.shipCompareToken += 1;
    s.shipCompare = [];
    s.shipCarrier = null;
    await loadShipOrders();
  }

  async function bookFtl() {
    const ids = Array.from(s.selShipFtl);
    if (!ids.length) {
      toast('Select at least one FTL order to book.', 'warning');
      return;
    }
    const r = await api(cfg.ftlBookUrl, { method: 'POST', body: { order_ids: ids } });
    toast(r.message || 'FTL orders booked successfully.', 'success');
    s.selShipFtl.clear();
    await loadShipFtl();
  }

  async function doSyncWh(id) {
    const r = await api(withId(cfg.warehouseSyncBaseUrl, id), { method: 'POST', body: {} });
    toast(r.alreadyExisted ? 'Warehouse was already linked to ShipDaak.' : 'Warehouse linked to ShipDaak successfully.', 'success');
    await loadWh();
  }

  function doLinkWh(id) {
    const warehouse = s.wh.find((w) => w.id === Number(id));
    if (!warehouse) return;
    q('courier-warehouse-link-id').value = String(warehouse.id);
    q('courier-warehouse-link-name').textContent = `${warehouse.name} (${warehouse.pincode})`;
    q('courier-warehouse-link-pickup').value = warehouse.shipdaak_pickup_id || '';
    q('courier-warehouse-link-rto').value = warehouse.shipdaak_rto_id || '';
    modal('courier-warehouse-link-modal', true);
  }

  async function saveWh(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form).entries());
    const r = await api(cfg.warehouseListUrl, { method: 'POST', body });
    toast(`Warehouse ${r.name || 'saved'} successfully.`, 'success');
    form.reset();
    closeModals();
    await loadWh();
  }

  async function doLinkWhSave(event) {
    event.preventDefault();
    const id = intOrNull(q('courier-warehouse-link-id')?.value);
    if (!id) {
      toast('Choose a valid warehouse first.', 'warning');
      return;
    }
    const body = {
      shipdaak_warehouse_id: q('courier-warehouse-link-pickup')?.value,
      rto_id: q('courier-warehouse-link-rto')?.value,
    };
    await api(withId(cfg.warehouseLinkBaseUrl, id), { method: 'POST', body });
    toast('Existing ShipDaak IDs linked successfully.', 'success');
    closeModals();
    await loadWh();
  }

  function toggle(ids, set, checked) {
    ids.forEach((id) => {
      if (!Number.isInteger(id)) return;
      if (checked) set.add(id);
      else set.delete(id);
    });
  }

  function bind() {
    const run = (fn) => Promise.resolve(fn()).catch((e) => toast(e.message || 'Something went wrong.', 'error'));

    document.addEventListener('click', (event) => {
      const closeBtn = event.target.closest('[data-close-modal]');
      if (closeBtn) {
        modal(closeBtn.dataset.closeModal, false);
        return;
      }

      if (event.target.classList?.contains('courier-modal')) {
        closeModals();
        return;
      }

      if (event.target.closest('#courier-open-create-warehouse')) {
        modal('courier-warehouse-modal', true);
        return;
      }

      const whSync = event.target.closest('[data-wh-sync]');
      if (whSync) {
        run(() => doSyncWh(whSync.dataset.whSync));
        return;
      }

      const whLink = event.target.closest('[data-wh-link]');
      if (whLink) {
        doLinkWh(whLink.dataset.whLink);
        return;
      }

      const orderTypeBtn = event.target.closest('[data-orders-type]');
      if (orderTypeBtn) {
        s.orderType = orderTypeBtn.dataset.ordersType;
        s.selOrders.clear();
        s.selFtl.clear();
        paintControls();
        run(() => (s.orderType === 'ftl' ? loadFtlOrders() : loadOrders()));
        return;
      }

      const orderStatusBtn = event.target.closest('[data-orders-status]');
      if (orderStatusBtn) {
        s.orderStatus = orderStatusBtn.dataset.ordersStatus;
        paintControls();
        run(loadOrders);
        return;
      }

      const ftlStatusBtn = event.target.closest('[data-ftl-status]');
      if (ftlStatusBtn) {
        s.ftlStatus = ftlStatusBtn.dataset.ftlStatus;
        paintControls();
        run(loadFtlOrders);
        return;
      }

      const shipTypeBtn = event.target.closest('[data-shipment-type]');
      if (shipTypeBtn) {
        s.shipType = shipTypeBtn.dataset.shipmentType;
        paintControls();
        run(() => (s.shipType === 'ftl' ? loadShipFtl() : loadShipOrders()));
        return;
      }

      const actions = {
        'courier-order-edit-action': () => {
          const id = Array.from(s.selOrders)[0];
          if (!id) return;
          window.location.href = withId(cfg.orderEditUrlTemplate, id);
        },
        'courier-order-book-awb-action': () => startShipBooking(),
        'courier-order-manifest-action': () => manifest(),
        'courier-order-cancel-action': () => cancelOrders(),
        'courier-order-invoice-action': () => invoices(),
        'courier-order-label-action': () => labels(),
        'courier-order-details-action': () => orderDetails(),
        'courier-order-track-action': () => tracking(),
        'courier-order-sync-action': () => syncStatuses(),
        'courier-order-delete-action': () => delOrders(),
        'courier-ftl-edit-action': () => {
          const id = Array.from(s.selFtl)[0];
          if (!id) return;
          window.location.href = withId(cfg.ftlOrderEditUrlTemplate, id);
        },
        'courier-ftl-cancel-action': () => cancelFtl(),
        'courier-ftl-delete-action': () => delFtl(),
        'courier-book-selected-carrier': () => bookCarrier(),
        'courier-ftl-book-action': () => bookFtl(),
      };

      const actionTarget = event.target.closest('[id]');
      const action = actionTarget ? actions[actionTarget.id] : null;
      if (action) run(action);
    });

    document.addEventListener('change', (event) => {
      if (event.target.matches('.order-box')) {
        toggle([intOrNull(event.target.value)], s.selOrders, event.target.checked);
        renderOrders();
        return;
      }
      if (event.target.matches('.ftl-box')) {
        toggle([intOrNull(event.target.value)], s.selFtl, event.target.checked);
        renderFtlOrders();
        return;
      }
      if (event.target.matches('.ship-box')) {
        toggle([intOrNull(event.target.value)], s.selShip, event.target.checked);
        renderShipOrders();
        void startShipBooking();
        return;
      }
      if (event.target.matches('.ship-ftl-box')) {
        toggle([intOrNull(event.target.value)], s.selShipFtl, event.target.checked);
        renderShipFtl();
        return;
      }
      if (event.target.id === 'courier-orders-select-all') {
        toggle(orderRows().map((o) => o.id), s.selOrders, event.target.checked);
        renderOrders();
        return;
      }
      if (event.target.id === 'courier-ftl-orders-select-all') {
        toggle(ftlRows().map((o) => o.id), s.selFtl, event.target.checked);
        renderFtlOrders();
        return;
      }
      if (event.target.id === 'courier-shipments-select-all') {
        toggle(shipRows().map((o) => o.id), s.selShip, event.target.checked);
        renderShipOrders();
        void startShipBooking();
        return;
      }
      if (event.target.id === 'courier-shipments-ftl-select-all') {
        toggle(s.shipFtl.map((o) => o.id), s.selShipFtl, event.target.checked);
        renderShipFtl();
        return;
      }
      if (event.target.matches('.ship-carrier-radio')) {
        s.shipCarrier = intOrNull(event.target.value);
        renderCompare();
        return;
      }
      if (event.target.id === 'courier-shipment-warehouse') {
        s.shipWh = intOrNull(event.target.value);
        void startShipBooking();
      }
    });

    q('courier-orders-search')?.addEventListener('input', (event) => {
      s.orderSearch = event.target.value.trim();
      if (s.orderType === 'ftl') renderFtlOrders();
      else renderOrders();
    });

    q('courier-orders-refresh')?.addEventListener('click', () => {
      run(() => (s.orderType === 'ftl' ? loadFtlOrders() : loadOrders()));
    });

    q('courier-shipments-search')?.addEventListener('input', (event) => {
      s.shipSearch = event.target.value.trim();
      if (s.shipType === 'ftl') renderShipFtl();
      else renderShipOrders();
    });

    q('courier-shipments-refresh')?.addEventListener('click', () => {
      run(() => (s.shipType === 'ftl' ? loadShipFtl() : loadShipOrders()));
    });

    q('courier-warehouse-form')?.addEventListener('submit', (event) => run(() => saveWh(event)));
    q('courier-warehouse-link-form')?.addEventListener('submit', (event) => run(() => doLinkWhSave(event)));

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeModals();
    });
  }

  async function init() {
    parseFlash();
    bind();
    paintControls();
    try {
      if (cfg.activeSection === 'orders') {
        if (s.orderType === 'ftl') await loadFtlOrders();
        else await loadOrders();
        return;
      }
      if (cfg.activeSection === 'shipments') {
        await Promise.all([loadWh(), s.shipType === 'ftl' ? loadShipFtl() : loadShipOrders()]);
        consumeShipSelection();
        return;
      }
      if (cfg.activeSection === 'warehouses') {
        await loadWh();
      }
    } catch (e) {
      toast(e.message || 'Unable to load courier workspace.', 'error');
    }
  }

  init();
})();
