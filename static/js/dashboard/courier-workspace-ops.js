(() => {
  const cfg = window.courierWorkspaceConfig;
  if (!cfg) return;

  const s = {
    wh: [], orderType: 'b2c', orderStatus: 'all', orderSearch: '', orders: [], selOrders: new Set(),
    ftlStatus: 'all', ftlOrders: [], selFtl: new Set(), shipType: 'b2c', shipOrders: [], selShip: new Set(),
    shipCarrier: null, shipCompare: [], shipWh: null, shipFtl: [], selShipFtl: new Set(), routes: {}
  };
  const q = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const num = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
  const intOrNull = (v) => Number.isInteger(parseInt(v, 10)) ? parseInt(v, 10) : null;
  const money = (v) => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(num(v));
  const pk = (u, id) => String(u).replace(/\/1(?=\/|$)/, `/${id}`);
  const join = (a, b) => `${String(a).replace(/\/+$/, '')}/${String(b).replace(/^\/+/, '')}`;
  const csrf = () => ((document.cookie.split(';').map(x => x.trim()).find(x => x.startsWith('csrftoken=')) || '').split('=').slice(1).join('='));
  const typeOfOrder = (o) => ((o?.carrier_type || '').toLowerCase() === 'b2b' || (o?.carrier_type || '').toLowerCase() === 'b2c') ? (o.carrier_type || '').toLowerCase() : (num(o?.applicable_weight ?? o?.weight) >= 20 ? 'b2b' : 'b2c');
  const badge = (st) => ({draft:'bg-amber-100 text-amber-700',booked:'bg-blue-100 text-blue-700',manifested:'bg-blue-100 text-blue-700',picked_up:'bg-indigo-100 text-indigo-700',out_for_delivery:'bg-indigo-100 text-indigo-700',delivered:'bg-emerald-100 text-emerald-700',cancelled:'bg-red-100 text-red-700'})[String(st||'').toLowerCase()] || 'bg-gray-100 text-gray-700';

  function toast(msg, type='info') {
    const c = q('courier-toast-container'); if (!c) return;
    const t = document.createElement('div');
    t.className = `pointer-events-auto rounded-2xl px-4 py-3 text-sm shadow-2xl text-white ${type==='success'?'bg-emerald-600':type==='error'?'bg-red-600':type==='warning'?'bg-amber-500':'bg-slate-900'}`;
    t.textContent = msg; c.appendChild(t); setTimeout(() => t.remove(), 4200);
  }

  function fmtError(data, status) {
    if (!data) return 'Request failed (' + status + ')';
    if (typeof data === 'string') return data;
    if (typeof data.detail === 'string' && data.detail.trim()) return data.detail;
    const parts = Object.entries(data)
      .filter(([k]) => k !== 'detail')
      .map(([k, v]) => {
        const text = Array.isArray(v) ? v.join(', ') : (typeof v === 'string' ? v : JSON.stringify(v));
        return k + ': ' + text;
      })
      .filter(Boolean);
    return parts.length ? parts.join(' | ') : 'Request failed (' + status + ')';
  }

  async function api(url, opts={}) {
    const h = new Headers(opts.headers || {}); h.set('Accept','application/json');
    if (opts.body && !(opts.body instanceof FormData)) { h.set('Content-Type','application/json'); opts.body = JSON.stringify(opts.body); }
    if ((opts.method || 'GET').toUpperCase() !== 'GET') h.set('X-CSRFToken', csrf());
    const r = await fetch(url, {...opts, headers:h}); const txt = await r.text(); let data = {};
    try { data = txt ? JSON.parse(txt) : {}; } catch { data = { detail: txt }; }
    if (!r.ok) throw new Error(fmtError(data, r.status)); return data;
  }

  async function blob(url, opts={}) {
    const h = new Headers(opts.headers || {});
    if (opts.body) { h.set('Content-Type','application/json'); opts.body = JSON.stringify(opts.body); }
    if ((opts.method || 'GET').toUpperCase() !== 'GET') h.set('X-CSRFToken', csrf());
    const r = await fetch(url, {...opts, headers:h}); if (!r.ok) throw new Error(await r.text() || 'Download failed');
    return { blob: await r.blob(), cd: r.headers.get('Content-Disposition') || '' };
  }

  function dl(file, name) { const u = URL.createObjectURL(file); const a = document.createElement('a'); a.href = u; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 500); }
  function modal(id, open) { const m = q(id); if (!m) return; m.classList.toggle('hidden', !open); document.body.classList.toggle('overflow-hidden', open); }
  function closeModals() { document.querySelectorAll('.courier-modal').forEach((m) => m.classList.add('hidden')); document.body.classList.remove('overflow-hidden'); }
  function arr(data) { return Array.isArray(data) ? data : (Array.isArray(data?.results) ? data.results : []); }
  function setActive(btns, fn) { btns.forEach((b) => { const on = fn(b); b.classList.toggle('bg-white', on); b.classList.toggle('text-blue-700', on); b.classList.toggle('shadow-sm', on); b.classList.toggle('text-gray-600', !on); }); }
  function empty(el, msg) { if (el) el.innerHTML = `<div class="rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-6 py-12 text-center text-sm text-gray-500">${esc(msg)}</div>`; }
  function whOptions() { return s.wh.filter((w) => w.is_active !== false).map((w) => `<option value="${w.id}">${esc(w.name)} (${esc(w.pincode)})</option>`).join(''); }

  function fillWhSelects() {
    const orderWh = q('courier-order-warehouse'); if (orderWh) orderWh.innerHTML = `<option value="">Select warehouse</option>${whOptions()}`;
    const shipWh = q('courier-shipment-warehouse'); if (shipWh) shipWh.innerHTML = `<option value="">Use sender pincode from order</option>${whOptions()}`;
  }
  function isWhLinked(w) { return !!(w?.shipdaak_pickup_id && w?.shipdaak_rto_id); }

  async function loadWh() { s.wh = arr(await api(cfg.warehouseListUrl)); fillWhSelects(); if (cfg.activeSection === 'warehouses') renderWh(); }
  function renderWh() {
    const el = q('courier-warehouse-list'); if (!el) return; if (!s.wh.length) return empty(el, 'No courier warehouses yet.');
    el.innerHTML = s.wh.map((w) => `<article class="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"><div><div class="flex items-center gap-3"><h3 class="text-lg font-semibold text-gray-900">${esc(w.name)}</h3><span class="rounded-full px-3 py-1 text-xs font-semibold ${w.shipdaak_pickup_id && w.shipdaak_rto_id ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}">${w.shipdaak_pickup_id && w.shipdaak_rto_id ? 'Synced' : 'Not Synced'}</span></div><p class="mt-2 text-sm text-gray-600">${esc(w.address)}${w.address_2 ? `, ${esc(w.address_2)}` : ''}</p><p class="mt-1 text-sm text-gray-600">${esc(w.city)}, ${esc(w.state)} â€¢ ${esc(w.pincode)}</p><p class="mt-1 text-sm text-gray-600">Contact: ${esc(w.contact_name)} (${esc(w.contact_no)})</p><p class="mt-3 text-xs text-gray-500">Pickup ID: ${esc(w.shipdaak_pickup_id || '-')} â€¢ RTO ID: ${esc(w.shipdaak_rto_id || '-')}</p></div><div class="flex flex-wrap gap-2"><button type="button" data-wh-sync="${w.id}" class="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Sync to Shipdaak</button><button type="button" data-wh-link="${w.id}" class="rounded-xl border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Link Existing IDs</button></div></div></article>`).join('');
  }

  function renderWh() {
    const el = q('courier-warehouse-list'); if (!el) return; if (!s.wh.length) return empty(el, 'No courier warehouses yet.');
    el.innerHTML = s.wh.map((w) => {
      const linked = isWhLinked(w);
      const createClasses = linked
        ? 'cursor-not-allowed rounded-xl bg-slate-300 px-4 py-2 text-sm font-semibold text-white'
        : 'rounded-xl bg-orange-600 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-700';
      const createLabel = linked ? 'Already Linked' : 'Create NEW in ShipDaak';
      const createTitle = linked
        ? 'This warehouse is already linked to ShipDaak.'
        : 'Creates a brand-new warehouse in ShipDaak. Use only if it does not already exist there.';
      const helperTone = linked
        ? 'rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-900'
        : 'rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900';
      const helperText = linked
        ? 'This local warehouse is already linked to ShipDaak.'
        : 'Important: if this warehouse already exists in ShipDaak, do not create a new one. Use Link Existing ShipDaak IDs instead.';
      return `<article class="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"><div class="min-w-0 flex-1"><div class="flex items-center gap-3"><h3 class="text-lg font-semibold text-gray-900">${esc(w.name)}</h3><span class="rounded-full px-3 py-1 text-xs font-semibold ${linked ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}">${linked ? 'Linked to ShipDaak' : 'Not Linked to ShipDaak'}</span></div><p class="mt-2 text-sm text-gray-600">${esc(w.address)}${w.address_2 ? `, ${esc(w.address_2)}` : ''}</p><p class="mt-1 text-sm text-gray-600">${esc(w.city)}, ${esc(w.state)} &middot; ${esc(w.pincode)}</p><p class="mt-1 text-sm text-gray-600">Contact: ${esc(w.contact_name)} (${esc(w.contact_no)})</p><p class="mt-3 text-xs text-gray-500">Pickup ID: ${esc(w.shipdaak_pickup_id || '-')} &middot; RTO ID: ${esc(w.shipdaak_rto_id || '-')}</p><div class="mt-4 ${helperTone}">${esc(helperText)}</div><p class="mt-2 text-xs text-gray-500">Link Existing ShipDaak IDs only saves the known ShipDaak pickup and RTO IDs on this local warehouse. It does not create anything in ShipDaak.</p></div><div class="flex flex-wrap gap-2 lg:max-w-xs lg:justify-end"><button type="button" data-wh-sync="${w.id}" class="${createClasses}" title="${esc(createTitle)}" ${linked ? 'disabled' : ''}>${createLabel}</button><button type="button" data-wh-link="${w.id}" class="rounded-xl border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50" title="Saves the existing ShipDaak pickup and RTO IDs locally without creating anything in ShipDaak.">Link Existing ShipDaak IDs</button></div></div></article>`;
    }).join('');
  }

  async function loadOrders() { const url = s.orderStatus === 'all' ? cfg.orderListUrl : `${cfg.orderListUrl}?status=${encodeURIComponent(s.orderStatus)}`; s.orders = arr(await api(url)); renderOrders(); }
  function renderOrders() {
    const el = q('courier-orders-list'); if (!el) return; let rows = s.orders.filter((o) => typeOfOrder(o) === s.orderType);
    if (s.orderSearch) { const n = s.orderSearch.toLowerCase(); rows = rows.filter((o) => [o.order_number,o.recipient_name,o.recipient_pincode,o.selected_carrier,o.awb_number].join(' ').toLowerCase().includes(n)); }
    if (!rows.length) return empty(el, `No ${s.orderType.toUpperCase()} orders found for this filter.`);
    el.innerHTML = rows.map((o) => `<article class="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><div class="flex items-start gap-3"><input type="checkbox" class="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 order-box" value="${o.id}" ${s.selOrders.has(o.id) ? 'checked' : ''}><div class="min-w-0 flex-1"><div class="flex flex-wrap items-start justify-between gap-3"><div><p class="text-sm font-semibold text-gray-900">${esc(o.order_number)}</p><p class="mt-1 text-sm text-gray-600">${esc(o.recipient_name)} â€¢ ${esc(o.recipient_pincode)}</p></div><span class="rounded-full px-3 py-1 text-xs font-semibold ${badge(o.status)}">${esc(String(o.status || '-').toUpperCase())}</span></div><div class="mt-4 grid gap-2 text-sm text-gray-600 sm:grid-cols-2"><p><span class="font-medium text-gray-800">Weight:</span> ${esc(o.applicable_weight ?? o.weight ?? '-')} kg</p><p><span class="font-medium text-gray-800">Payment:</span> ${esc(String(o.payment_mode || '-').toUpperCase())}</p><p><span class="font-medium text-gray-800">Warehouse:</span> ${esc(o.warehouse_name || o.courier_warehouse_name || '-')}</p><p><span class="font-medium text-gray-800">AWB:</span> ${esc(o.awb_number || '-')}</p></div>${o.selected_carrier ? `<div class="mt-4 rounded-2xl bg-blue-50 px-4 py-3 text-sm text-blue-900"><span class="font-semibold">Carrier:</span> ${esc(o.selected_carrier)}</div>` : ''}</div></div></article>`).join('');
    updateOrderActions();
  }
  async function loadFtlOrders() { const url = s.ftlStatus === 'all' ? cfg.ftlOrderListUrl : `${cfg.ftlOrderListUrl}?status=${encodeURIComponent(s.ftlStatus)}`; s.ftlOrders = arr(await api(url)); renderFtlOrders(); }
  function renderFtlOrders() {
    const el = q('courier-ftl-orders-list'); if (!el) return; const rows = s.ftlStatus === 'all' ? s.ftlOrders : s.ftlOrders.filter((o) => o.status === s.ftlStatus);
    if (!rows.length) return empty(el, 'No FTL orders found for this filter.');
    el.innerHTML = rows.map((o) => `<article class="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><div class="flex items-start gap-3"><input type="checkbox" class="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 ftl-box" value="${o.id}" ${s.selFtl.has(o.id) ? 'checked' : ''}><div class="min-w-0 flex-1"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold text-gray-900">${esc(o.order_number)}</p><p class="mt-1 text-sm text-gray-600">${esc(o.name)} â€¢ ${esc(o.phone)}</p></div><span class="rounded-full px-3 py-1 text-xs font-semibold ${badge(o.status)}">${esc(String(o.status || '-').toUpperCase())}</span></div><div class="mt-4 grid gap-2 text-sm text-gray-600 sm:grid-cols-2"><p><span class="font-medium text-gray-800">Route:</span> ${esc(o.source_city)} to ${esc(o.destination_city)}</p><p><span class="font-medium text-gray-800">Container:</span> ${esc(o.container_type)}</p><p><span class="font-medium text-gray-800">Base:</span> ${money(o.base_price)}</p><p><span class="font-medium text-gray-800">Total:</span> ${money(o.total_price)}</p></div></div></div></article>`).join('');
    updateFtlActions();
  }

  function updateOrderActions() {
    const bar = q('courier-orders-actions'); if (!bar) return; const rows = s.orders.filter((o) => s.selOrders.has(o.id)); const count = rows.length;
    bar.classList.toggle('hidden', count === 0); q('courier-orders-selected-count').textContent = `${count} selected`;
    const allDraft = count && rows.every((o) => o.status === 'draft'); const allBooked = count && rows.every((o) => o.status === 'booked'); const anyAwb = rows.some((o) => o.awb_number);
    q('courier-order-edit-action').classList.toggle('hidden', !(count === 1 && allDraft));
    q('courier-order-book-awb-action').classList.toggle('hidden', !allDraft);
    q('courier-order-manifest-action').classList.toggle('hidden', !rows.some((o) => ['booked','manifested'].includes(o.status) && o.awb_number));
    q('courier-order-cancel-action').classList.toggle('hidden', !allBooked);
    q('courier-order-label-action').classList.toggle('hidden', !anyAwb);
    q('courier-order-details-action').classList.toggle('hidden', count !== 1);
    q('courier-order-track-action').classList.toggle('hidden', !(count === 1 && anyAwb));
    q('courier-order-sync-action').classList.toggle('hidden', !anyAwb);
  }
  function updateFtlActions() {
    const bar = q('courier-ftl-orders-actions'); if (!bar) return; const rows = s.ftlOrders.filter((o) => s.selFtl.has(o.id));
    bar.classList.toggle('hidden', rows.length === 0); q('courier-ftl-orders-selected-count').textContent = `${rows.length} selected`;
    q('courier-ftl-edit-action').classList.toggle('hidden', !(rows.length === 1 && rows[0].status === 'draft'));
    q('courier-ftl-cancel-action').classList.toggle('hidden', !(rows.length && rows.every((o) => o.status === 'booked')));
  }

  async function loadShipOrders() { s.shipOrders = arr(await api(`${cfg.orderListUrl}?status=draft`)).filter((o) => typeOfOrder(o) === s.shipType); renderShipOrders(); consumeShipSelection(); }
  function renderShipOrders() {
    const el = q('courier-shipment-orders-list'); if (!el) return; q('courier-shipments-heading').textContent = `Select ${s.shipType.toUpperCase()} Orders to Ship`; q('courier-shipment-selection-count').textContent = `${s.selShip.size} selected`;
    if (!s.shipOrders.length) return empty(el, `No ${s.shipType.toUpperCase()} draft orders are available.`);
    el.innerHTML = s.shipOrders.map((o) => `<label class="flex items-start gap-3 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm hover:border-blue-200"><input type="checkbox" class="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 ship-box" value="${o.id}" ${s.selShip.has(o.id) ? 'checked' : ''}><div class="min-w-0 flex-1"><p class="text-sm font-semibold text-gray-900">${esc(o.order_number)}</p><p class="mt-1 text-sm text-gray-600">${esc(o.recipient_name)} â€¢ ${esc(o.recipient_pincode)}</p><p class="mt-2 text-xs text-gray-500">Weight: ${esc(o.applicable_weight ?? o.weight ?? '-')} kg â€¢ ${esc(String(o.payment_mode || '-').toUpperCase())}</p></div></label>`).join('');
    renderCompare();
  }
  function renderCompare() {
    const el = q('courier-shipment-comparison'); if (!el) return; q('courier-shipment-selection-count').textContent = `${s.selShip.size} selected`;
    if (!s.selShip.size) return empty(el, 'Select draft orders to compare carrier rates.');
    if (!s.shipCompare.length) return empty(el, 'Compare carriers to see eligible booking options.');
    el.innerHTML = s.shipCompare.map((c, i) => `<label class="block rounded-2xl border border-gray-200 bg-white p-4 shadow-sm hover:border-blue-200"><div class="flex items-start gap-3"><input type="radio" name="ship-carrier" class="mt-1 h-4 w-4 border-gray-300 text-blue-600 focus:ring-blue-500 ship-carrier-radio" value="${i}" ${s.shipCarrier === i ? 'checked' : ''}><div class="min-w-0 flex-1"><div class="flex flex-wrap items-start justify-between gap-3"><div><p class="text-sm font-semibold text-gray-900">${esc(c.carrier || c.carrier_name || 'Carrier')}</p><p class="mt-1 text-xs text-gray-500">${esc(c.mode || '-')} â€¢ ${esc(c.applied_zone || c.zone || '-')} â€¢ ${esc(c.service_category || 'Forward')}</p></div><div class="text-right"><p class="text-sm font-semibold text-blue-700">${money(c.total_cost)}</p></div></div></div></div></label>`).join('') + `<div class="mt-4 flex items-center justify-between rounded-2xl bg-gray-50 px-4 py-3"><p class="text-xs text-gray-500">Booking preserves the carrier's full aggregator/service identity.</p><button type="button" id="courier-book-selected-carrier" class="rounded-xl bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700">Book Selected Carrier</button></div>`;
  }
  async function compareCarriers() {
    if (!s.selShip.size) { s.shipCompare = []; s.shipCarrier = null; return renderCompare(); }
    try {
      const body = { order_ids: Array.from(s.selShip), business_type: s.shipType }; if (s.shipWh) body.warehouse_id = s.shipWh;
      s.shipCompare = arr((await api(cfg.compareCarriersUrl, { method: 'POST', body })).carriers || []).filter((c) => String(c.service_category || '').toLowerCase() !== 'rvp');
      s.shipCarrier = null; renderCompare();
    } catch (e) { s.shipCompare = []; s.shipCarrier = null; renderCompare(); toast(e.message, 'error'); }
  }

  async function loadShipFtl() { s.shipFtl = arr(await api(`${cfg.ftlOrderListUrl}?status=draft`)); renderShipFtl(); }
  function renderShipFtl() {
    const el = q('courier-shipments-ftl-list'); if (!el) return; const bar = q('courier-shipments-ftl-actions');
    if (!s.shipFtl.length) { if (bar) bar.classList.add('hidden'); return empty(el, 'No draft FTL orders are waiting for booking.'); }
    if (bar) bar.classList.toggle('hidden', s.selShipFtl.size === 0); q('courier-shipments-ftl-selected-count').textContent = `${s.selShipFtl.size} selected`;
    el.innerHTML = s.shipFtl.map((o) => `<label class="block rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><div class="flex items-start gap-3"><input type="checkbox" class="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 ship-ftl-box" value="${o.id}" ${s.selShipFtl.has(o.id) ? 'checked' : ''}><div class="min-w-0 flex-1"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold text-gray-900">${esc(o.order_number)}</p><p class="mt-1 text-sm text-gray-600">${esc(o.source_city)} to ${esc(o.destination_city)}</p></div><span class="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700">${esc(o.container_type)}</span></div><p class="mt-3 text-sm text-gray-500">${money(o.total_price)}</p></div></div></label>`).join('');
  }

  async function loadRoutes() { s.routes = await api(cfg.ftlRoutesUrl); fillRouteSelects(); }
  function fillRouteSelects() {
    const src = q('courier-ftl-source-city'), dst = q('courier-ftl-destination-city'), box = q('courier-ftl-container-type'); if (!src || !dst || !box) return;
    const curSrc = src.value; src.innerHTML = `<option value="">Select source</option>${Object.keys(s.routes).sort().map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join('')}`; if (curSrc) src.value = curSrc; fillDestAndBoxes();
  }
  function fillDestAndBoxes() {
    const src = q('courier-ftl-source-city'), dst = q('courier-ftl-destination-city'), box = q('courier-ftl-container-type'); if (!src || !dst || !box) return;
    const curDst = dst.value, curBox = box.value; const ds = src.value && s.routes[src.value] ? Object.keys(s.routes[src.value]).sort() : [];
    dst.innerHTML = `<option value="">Select destination</option>${ds.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join('')}`; if (ds.includes(curDst)) dst.value = curDst;
    const cs = src.value && dst.value && s.routes[src.value]?.[dst.value] ? s.routes[src.value][dst.value] : [];
    box.innerHTML = `<option value="">Select container</option>${cs.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join('')}`; if (cs.includes(curBox)) box.value = curBox;
  }
  async function previewFtl() {
    const src = q('courier-ftl-source-city'), dst = q('courier-ftl-destination-city'), box = q('courier-ftl-container-type'), p = q('courier-ftl-pricing-preview');
    if (!src?.value || !dst?.value || !box?.value || !p) { if (p) { p.classList.add('hidden'); p.innerHTML=''; } return; }
    try {
      const r = await api(cfg.ftlRateUrl, { method: 'POST', body: { source_city: src.value, destination_city: dst.value, container_type: box.value } });
      p.classList.remove('hidden'); p.innerHTML = `<div class="grid gap-3 sm:grid-cols-3"><div><p class="text-xs font-semibold uppercase tracking-wide text-blue-700">Base</p><p class="mt-1 text-lg font-semibold text-blue-900">${money(r.base_price)}</p></div><div><p class="text-xs font-semibold uppercase tracking-wide text-blue-700">GST</p><p class="mt-1 text-lg font-semibold text-blue-900">${money(r.gst_amount)}</p></div><div><p class="text-xs font-semibold uppercase tracking-wide text-blue-700">Total</p><p class="mt-1 text-lg font-semibold text-blue-900">${money(r.total_price)}</p></div></div>`;
    } catch { p.classList.add('hidden'); p.innerHTML=''; }
  }
  function openOrder(order, orderType = s.orderType) {
    q('courier-order-form')?.reset(); q('courier-order-edit-id').value = order?.id || ''; q('courier-order-modal-title').textContent = order ? `Edit ${order.order_number}` : orderType === 'b2b' ? 'Create B2B Order' : 'Create B2C Order'; q('courier-order-submit').textContent = order ? 'Save Changes' : 'Save Order'; fillWhSelects();
    const map = { 'courier-order-recipient-name': order?.recipient_name, 'courier-order-recipient-contact': order?.recipient_contact, 'courier-order-recipient-address': order?.recipient_address, 'courier-order-recipient-pincode': order?.recipient_pincode, 'courier-order-recipient-city': order?.recipient_city, 'courier-order-recipient-state': order?.recipient_state, 'courier-order-recipient-email': order?.recipient_email, 'courier-order-sender-pincode': order?.sender_pincode, 'courier-order-sender-name': order?.sender_name, 'courier-order-sender-address': order?.sender_address, 'courier-order-sender-phone': order?.sender_phone, 'courier-order-weight': order?.weight, 'courier-order-length': order?.length, 'courier-order-width': order?.width, 'courier-order-height': order?.height, 'courier-order-payment-mode': order?.payment_mode || 'prepaid', 'courier-order-value': order?.order_value ?? 0, 'courier-order-item-type': order?.item_type, 'courier-order-sku': order?.sku, 'courier-order-quantity': order?.quantity ?? 1, 'courier-order-item-amount': order?.item_amount ?? 0 };
    Object.entries(map).forEach(([id, v]) => { const el = q(id); if (el) el.value = v == null ? '' : String(v); }); if (q('courier-order-warehouse')) q('courier-order-warehouse').value = order?.warehouse || order?.courier_warehouse_id || '';
    modal('courier-order-modal', true);
  }
  function openFtl(order) {
    q('courier-ftl-form')?.reset(); q('courier-ftl-edit-id').value = order?.id || ''; q('courier-ftl-modal-title').textContent = order ? `Edit ${order.order_number}` : 'Create FTL Order'; q('courier-ftl-submit').textContent = order ? 'Save Changes' : 'Save FTL Order'; fillRouteSelects();
    const map = { 'courier-ftl-name': order?.name, 'courier-ftl-phone': order?.phone, 'courier-ftl-email': order?.email, 'courier-ftl-source-city': order?.source_city, 'courier-ftl-source-pincode': order?.source_pincode, 'courier-ftl-source-address': order?.source_address, 'courier-ftl-destination-city': order?.destination_city, 'courier-ftl-destination-pincode': order?.destination_pincode, 'courier-ftl-destination-address': order?.destination_address, 'courier-ftl-container-type': order?.container_type, 'courier-ftl-notes': order?.notes };
    Object.entries(map).forEach(([id, v]) => { const el = q(id); if (el) el.value = v == null ? '' : String(v); }); previewFtl(); modal('courier-ftl-modal', true);
  }

  async function saveOrder(e) {
    e.preventDefault();
    const form = q('courier-order-form');
    if (form && !form.reportValidity()) {
      const invalid = form.querySelector(':invalid');
      invalid?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      invalid?.focus({ preventScroll: true });
      toast('Please complete the required order fields.', 'warning');
      return;
    }
    const editId = q('courier-order-edit-id').value;
    const body = { recipient_name:q('courier-order-recipient-name').value.trim(), recipient_contact:q('courier-order-recipient-contact').value.trim(), recipient_address:q('courier-order-recipient-address').value.trim(), recipient_pincode:intOrNull(q('courier-order-recipient-pincode').value), recipient_city:q('courier-order-recipient-city').value.trim(), recipient_state:q('courier-order-recipient-state').value.trim(), recipient_email:q('courier-order-recipient-email').value.trim(), sender_pincode:intOrNull(q('courier-order-sender-pincode').value), sender_name:q('courier-order-sender-name').value.trim(), sender_address:q('courier-order-sender-address').value.trim(), sender_phone:q('courier-order-sender-phone').value.trim(), weight:num(q('courier-order-weight').value), length:num(q('courier-order-length').value), width:num(q('courier-order-width').value), height:num(q('courier-order-height').value), payment_mode:q('courier-order-payment-mode').value, order_value:num(q('courier-order-value').value), item_type:q('courier-order-item-type').value.trim(), sku:q('courier-order-sku').value.trim(), quantity:intOrNull(q('courier-order-quantity').value)||1, item_amount:num(q('courier-order-item-amount').value), warehouse:intOrNull(q('courier-order-warehouse').value) };
    const url = editId ? join(cfg.orderListUrl, String(editId) + '/') : cfg.orderListUrl;
    await api(url, { method: editId ? 'PATCH' : 'POST', body });
    closeModals();
    toast(editId ? 'Order updated.' : 'Order created.', 'success');
    await loadOrders();
  }
  async function saveFtl(e) {
    e.preventDefault();
    const editId = q('courier-ftl-edit-id').value;
    const body = { name:q('courier-ftl-name').value.trim(), phone:q('courier-ftl-phone').value.trim(), email:q('courier-ftl-email').value.trim(), source_city:q('courier-ftl-source-city').value, source_pincode:intOrNull(q('courier-ftl-source-pincode').value), source_address:q('courier-ftl-source-address').value.trim(), destination_city:q('courier-ftl-destination-city').value, destination_pincode:intOrNull(q('courier-ftl-destination-pincode').value), destination_address:q('courier-ftl-destination-address').value.trim(), container_type:q('courier-ftl-container-type').value, notes:q('courier-ftl-notes').value.trim() };
    await api(editId ? join(cfg.ftlOrderListUrl, String(editId) + '/') : cfg.ftlOrderListUrl, { method: editId ? 'PATCH' : 'POST', body }); closeModals(); toast(editId ? 'FTL order updated.' : 'FTL order created.', 'success'); await loadFtlOrders(); if (cfg.activeSection === 'shipments') await loadShipFtl();
  }
  async function saveWh(e) { e.preventDefault(); await api(cfg.warehouseListUrl, { method: 'POST', body: Object.fromEntries(new FormData(q('courier-warehouse-form')).entries()) }); closeModals(); toast('Warehouse created.', 'success'); await loadWh(); }

  async function doEditOrder() { const id = Array.from(s.selOrders)[0]; if (!id) return; openOrder(await api(join(cfg.orderListUrl, `${id}/`))); }
  async function doEditFtl() { const id = Array.from(s.selFtl)[0]; if (!id) return; openFtl(await api(join(cfg.ftlOrderListUrl, `${id}/`))); }
  async function deleteSelected(url, ids) { for (const id of ids) await api(join(url, `${id}/`), { method: 'DELETE' }); }
  async function postEach(url, ids, suffix) { for (const id of ids) await api(join(url, `${id}/${suffix}/`), { method: 'POST', body: {} }); }
  async function cancelOrders() { const ids = Array.from(s.selOrders); if (!ids.length || !confirm(`Cancel booking for ${ids.length} order(s)?`)) return; await postEach(cfg.orderListUrl, ids, 'cancel'); toast('Booking cancelled.', 'success'); await loadOrders(); }
  async function cancelFtl() { const ids = Array.from(s.selFtl); if (!ids.length || !confirm(`Cancel ${ids.length} FTL booking(s)?`)) return; await postEach(cfg.ftlOrderListUrl, ids, 'cancel'); toast('FTL bookings cancelled.', 'success'); await loadFtlOrders(); }
  async function delOrders() { const ids = Array.from(s.selOrders); if (!ids.length || !confirm(`Delete ${ids.length} order(s)?`)) return; await deleteSelected(cfg.orderListUrl, ids); s.selOrders.clear(); toast('Orders deleted.', 'success'); await loadOrders(); }
  async function delFtl() { const ids = Array.from(s.selFtl); if (!ids.length || !confirm(`Delete ${ids.length} FTL order(s)?`)) return; await deleteSelected(cfg.ftlOrderListUrl, ids); s.selFtl.clear(); toast('FTL orders deleted.', 'success'); await loadFtlOrders(); }
  async function syncStatuses() { const ids = Array.from(s.selOrders); if (!ids.length) return; await api(join(cfg.orderListUrl, 'shipdaak/sync-statuses/'), { method: 'POST', body: { order_ids: ids } }); toast('Statuses synced.', 'success'); await loadOrders(); }
  async function orderDetails() { const id = Array.from(s.selOrders)[0]; if (!id) return; const o = await api(join(cfg.orderListUrl, `${id}/`)); q('courier-order-details-subtitle').textContent = o.order_number || '-'; q('courier-order-details-content').innerHTML = [['Recipient',o.recipient_name],['Contact',o.recipient_contact],['Status',o.status],['Warehouse',o.warehouse_name || o.courier_warehouse_name],['AWB',o.awb_number],['Carrier',o.selected_carrier || o.carrier],['Weight',o.applicable_weight ?? o.weight],['Payment',o.payment_mode],['Order Value',o.order_value],['Total Cost',o.total_cost],['Zone',o.zone_applied],['Mode',o.mode]].map(([k,v]) => `<div class="rounded-2xl border border-gray-200 bg-gray-50 p-4"><p class="text-xs font-semibold uppercase tracking-wide text-gray-500">${esc(k)}</p><p class="mt-2 text-sm font-medium text-gray-900 break-words">${esc(v == null || v === '' ? '-' : v)}</p></div>`).join(''); modal('courier-order-details-modal', true); }
  async function tracking() { const id = Array.from(s.selOrders)[0]; if (!id) return; const o = await api(join(cfg.orderListUrl, `${id}/`)); const p = await api(pk(cfg.shipmentTrackBaseUrl, id)); const list = [p?.shipment_track_activities,p?.tracking,p?.tracking_data,p?.data?.tracking,p?.data?.tracking_data,p?.activities].find((x) => Array.isArray(x) && x.length) || []; q('courier-tracking-subtitle').textContent = `${o.order_number} â€¢ ${o.awb_number || 'No AWB'}`; q('courier-tracking-content').innerHTML = list.length ? list.map((x, i) => `<div class="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold text-gray-900">${esc(x.status || x.activity || x.description || `Event ${i+1}`)}</p><p class="mt-1 text-sm text-gray-600">${esc(x.message || x.description || x.location || x.event || '-')}</p></div><span class="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">${esc(x.date || x.datetime || x.created_at || x.time || '-')}</span></div></div>`).join('') : `<div class="rounded-2xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600"><pre class="overflow-x-auto whitespace-pre-wrap text-xs">${esc(JSON.stringify(p, null, 2))}</pre></div>`; modal('courier-tracking-modal', true); }
  async function invoices() { const ids = Array.from(s.selOrders); if (!ids.length) return; if (ids.length === 1) { const f = await blob(pk(cfg.singleInvoiceBaseUrl, ids[0])); dl(f.blob, 'courier-invoice.pdf'); } else { const f = await blob(cfg.multiInvoiceUrl, { method: 'POST', body: { order_ids: ids } }); dl(f.blob, 'courier-invoices.zip'); } }
  function selectedOrders() { return s.orders.filter((o) => s.selOrders.has(o.id)); }
  async function labels() { const awbs = selectedOrders().map((o) => o.awb_number).filter(Boolean); if (!awbs.length) return toast('Selected orders do not have AWBs.', 'warning'); const r = await api(cfg.bulkLabelUrl, { method: 'POST', body: { awb_numbers: [...new Set(awbs)] } }); if (r.label_url) window.open(r.label_url, '_blank', 'noopener,noreferrer'); toast('Label request sent.', 'success'); }
  async function manifest() { const awbs = selectedOrders().filter((o) => ['booked','manifested'].includes(o.status) && o.awb_number).map((o) => o.awb_number); if (!awbs.length) return toast('Select booked or manifested orders with AWBs.', 'warning'); const r = await api(cfg.manifestUrl, { method: 'POST', body: { awb_numbers: [...new Set(awbs)] } }); const u = r.manifest_url || r.url || r.manifest; if (u) window.open(u, '_blank', 'noopener,noreferrer'); toast('Manifest generated.', 'success'); }
  function startShipBooking() { sessionStorage.setItem('courier_shipment_selection', JSON.stringify({ business_type: s.orderType, order_ids: Array.from(s.selOrders), created_at_ms: Date.now() })); window.location.href = window.location.pathname.replace('orders-dashboard/', 'shipments/'); }
  function consumeShipSelection() { try { const raw = JSON.parse(sessionStorage.getItem('courier_shipment_selection') || 'null'); if (!raw || raw.business_type !== s.shipType) return; const ids = new Set(arr(raw.order_ids).map((id) => intOrNull(id)).filter(Boolean)); s.selShip = new Set(s.shipOrders.filter((o) => ids.has(o.id)).map((o) => o.id)); sessionStorage.removeItem('courier_shipment_selection'); renderShipOrders(); compareCarriers(); } catch { sessionStorage.removeItem('courier_shipment_selection'); } }
  async function bookCarrier() { if (s.shipCarrier == null) return toast('Select a carrier first.', 'warning'); const c = s.shipCompare[s.shipCarrier]; const body = { order_ids: Array.from(s.selShip), business_type: s.shipType, use_global_account: !!q('courier-use-global-account')?.checked }; if (c.carrier_id || c.id) body.carrier_id = c.carrier_id || c.id; else { body.carrier_name = c.carrier || c.carrier_name; body.mode = c.mode; } if (s.shipWh) body.warehouse_id = s.shipWh; await api(cfg.bookCarrierUrl, { method: 'POST', body }); s.selShip.clear(); s.shipCompare = []; s.shipCarrier = null; toast('Carrier booked successfully.', 'success'); await loadOrders(); await loadShipOrders(); }
  async function bookFtlShipments() { const ids = Array.from(s.selShipFtl); if (!ids.length) return; await api(cfg.ftlBookUrl, { method: 'POST', body: { order_ids: ids } }); s.selShipFtl.clear(); toast('FTL orders booked.', 'success'); await loadShipFtl(); await loadFtlOrders(); }
  async function doSyncWh(id) {
    const warehouse = s.wh.find((w) => Number(w.id) === Number(id));
    if (!warehouse) return;
    if (isWhLinked(warehouse)) return toast('This warehouse is already linked to ShipDaak.', 'info');
    if (!confirm('This will create a brand-new warehouse in ShipDaak. If the warehouse already exists in ShipDaak, cancel and use Link Existing ShipDaak IDs instead.')) return;
    const result = await api(pk(cfg.warehouseSyncBaseUrl, id), { method: 'POST', body: {} });
    toast(result?.alreadyExisted ? 'Existing ShipDaak IDs reused for this warehouse.' : 'New ShipDaak warehouse created and linked.', 'success');
    await loadWh();
  }
  async function doLinkWh(e) {
    e.preventDefault();
    const id = intOrNull(q('courier-warehouse-link-id').value);
    if (!id) return;
    await api(pk(cfg.warehouseLinkBaseUrl, id), { method: 'POST', body: { shipdaak_warehouse_id: intOrNull(q('courier-warehouse-link-pickup').value), rto_id: intOrNull(q('courier-warehouse-link-rto').value) } });
    closeModals();
    toast('Existing ShipDaak IDs saved locally.', 'success');
    await loadWh();
  }

  function updateCreateOrderButton() {
    const btn = q('courier-open-create-order');
    if (!btn) return;
    btn.textContent = s.orderType === 'ftl'
      ? 'Create FTL Order'
      : s.orderType === 'b2b'
        ? 'Create B2B Order'
        : 'Create B2C Order';
  }

  function setRecipientGeo(city = '', state = '') {
    const cityEl = q('courier-order-recipient-city');
    const stateEl = q('courier-order-recipient-state');
    if (cityEl) cityEl.value = city || '';
    if (stateEl) stateEl.value = state || '';
  }

  async function lookupPin() {
    const pin = String(q('courier-order-recipient-pincode')?.value || '').trim();
    if (!/^\d{6}$/.test(pin)) { setRecipientGeo('', ''); return; }
    try {
      const r = await api(String(cfg.lookupPincodeUrlTemplate).replace('111111', pin));
      setRecipientGeo(r.city || '', r.state || '');
    } catch (e) {
      setRecipientGeo('', '');
      toast(e.message, 'warning');
    }
  }
  function bind() {
    document.querySelectorAll('.courier-modal').forEach((m) => m.addEventListener('click', (e) => { if (e.target === m) closeModals(); }));
    document.querySelectorAll('[data-close-modal]').forEach((b) => b.addEventListener('click', closeModals));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModals(); });
    q('courier-open-create-order')?.addEventListener('click', () => { if (s.orderType === 'ftl') openFtl(null); else openOrder(null, s.orderType); });
    q('courier-open-create-warehouse')?.addEventListener('click', () => modal('courier-warehouse-modal', true));
    q('courier-order-form')?.addEventListener('submit', (e) => saveOrder(e).catch((x) => toast(x.message, 'error')));
    q('courier-ftl-form')?.addEventListener('submit', (e) => saveFtl(e).catch((x) => toast(x.message, 'error')));
    q('courier-warehouse-form')?.addEventListener('submit', (e) => saveWh(e).catch((x) => toast(x.message, 'error')));
    q('courier-warehouse-link-form')?.addEventListener('submit', (e) => doLinkWh(e).catch((x) => toast(x.message, 'error')));
    q('courier-order-recipient-pincode')?.addEventListener('input', (e) => {
      const pin = String(e.target.value || '').trim();
      if (/^\d{6}$/.test(pin)) lookupPin().catch((x) => toast(x.message, 'warning'));
      else setRecipientGeo('', '');
    });
    q('courier-order-recipient-pincode')?.addEventListener('blur', lookupPin);
    q('courier-orders-search')?.addEventListener('input', (e) => { s.orderSearch = e.target.value.trim(); renderOrders(); });
    q('courier-orders-refresh')?.addEventListener('click', () => loadOrders().catch((x) => toast(x.message, 'error')));
    q('courier-shipments-refresh')?.addEventListener('click', async () => { if (s.shipType === 'ftl') await loadShipFtl(); else await loadShipOrders(); toast('Shipment queue refreshed.', 'success'); });
    document.querySelectorAll('[data-orders-type]').forEach((b) => b.addEventListener('click', () => { s.orderType = b.dataset.ordersType; s.selOrders.clear(); updateCreateOrderButton(); setActive([...document.querySelectorAll('[data-orders-type]')], (x) => x.dataset.ordersType === s.orderType); q('courier-orders-regular-pane').classList.toggle('hidden', s.orderType === 'ftl'); q('courier-orders-ftl-pane').classList.toggle('hidden', s.orderType !== 'ftl'); if (s.orderType === 'ftl') loadFtlOrders().catch((x) => toast(x.message, 'error')); else renderOrders(); }));
    document.querySelectorAll('[data-orders-status]').forEach((b) => b.addEventListener('click', () => { s.orderStatus = b.dataset.ordersStatus; s.selOrders.clear(); setActive([...document.querySelectorAll('[data-orders-status]')], (x) => x.dataset.ordersStatus === s.orderStatus); loadOrders().catch((x) => toast(x.message, 'error')); }));
    document.querySelectorAll('[data-ftl-status]').forEach((b) => b.addEventListener('click', () => { s.ftlStatus = b.dataset.ftlStatus; s.selFtl.clear(); setActive([...document.querySelectorAll('[data-ftl-status]')], (x) => x.dataset.ftlStatus === s.ftlStatus); loadFtlOrders().catch((x) => toast(x.message, 'error')); }));
    document.querySelectorAll('[data-shipment-type]').forEach((b) => b.addEventListener('click', () => { s.shipType = b.dataset.shipmentType; s.selShip.clear(); s.shipCompare = []; s.shipCarrier = null; setActive([...document.querySelectorAll('[data-shipment-type]')], (x) => x.dataset.shipmentType === s.shipType); q('courier-shipments-regular-pane').classList.toggle('hidden', s.shipType === 'ftl'); q('courier-shipments-ftl-pane').classList.toggle('hidden', s.shipType !== 'ftl'); if (s.shipType === 'ftl') loadShipFtl().catch((x) => toast(x.message, 'error')); else loadShipOrders().catch((x) => toast(x.message, 'error')); }));
    q('courier-order-edit-action')?.addEventListener('click', () => doEditOrder().catch((x) => toast(x.message, 'error')));
    q('courier-order-book-awb-action')?.addEventListener('click', startShipBooking);
    q('courier-order-manifest-action')?.addEventListener('click', () => manifest().catch((x) => toast(x.message, 'error')));
    q('courier-order-cancel-action')?.addEventListener('click', () => cancelOrders().catch((x) => toast(x.message, 'error')));
    q('courier-order-invoice-action')?.addEventListener('click', () => invoices().catch((x) => toast(x.message, 'error')));
    q('courier-order-label-action')?.addEventListener('click', () => labels().catch((x) => toast(x.message, 'error')));
    q('courier-order-details-action')?.addEventListener('click', () => orderDetails().catch((x) => toast(x.message, 'error')));
    q('courier-order-track-action')?.addEventListener('click', () => tracking().catch((x) => toast(x.message, 'error')));
    q('courier-order-sync-action')?.addEventListener('click', () => syncStatuses().catch((x) => toast(x.message, 'error')));
    q('courier-order-delete-action')?.addEventListener('click', () => delOrders().catch((x) => toast(x.message, 'error')));
    q('courier-ftl-edit-action')?.addEventListener('click', () => doEditFtl().catch((x) => toast(x.message, 'error')));
    q('courier-ftl-cancel-action')?.addEventListener('click', () => cancelFtl().catch((x) => toast(x.message, 'error')));
    q('courier-ftl-delete-action')?.addEventListener('click', () => delFtl().catch((x) => toast(x.message, 'error')));
    q('courier-ftl-book-action')?.addEventListener('click', () => bookFtlShipments().catch((x) => toast(x.message, 'error')));
    q('courier-orders-list')?.addEventListener('change', (e) => { if (!e.target.classList.contains('order-box')) return; const id = intOrNull(e.target.value); if (!id) return; e.target.checked ? s.selOrders.add(id) : s.selOrders.delete(id); updateOrderActions(); });
    q('courier-ftl-orders-list')?.addEventListener('change', (e) => { if (!e.target.classList.contains('ftl-box')) return; const id = intOrNull(e.target.value); if (!id) return; e.target.checked ? s.selFtl.add(id) : s.selFtl.delete(id); updateFtlActions(); });
    q('courier-shipment-orders-list')?.addEventListener('change', (e) => { if (!e.target.classList.contains('ship-box')) return; const id = intOrNull(e.target.value); if (!id) return; e.target.checked ? s.selShip.add(id) : s.selShip.delete(id); compareCarriers(); });
    q('courier-shipment-comparison')?.addEventListener('change', (e) => { if (e.target.classList.contains('ship-carrier-radio')) s.shipCarrier = intOrNull(e.target.value); });
    q('courier-shipment-comparison')?.addEventListener('click', (e) => { if (e.target.id === 'courier-book-selected-carrier') bookCarrier().catch((x) => toast(x.message, 'error')); });
    q('courier-shipment-warehouse')?.addEventListener('change', (e) => { s.shipWh = intOrNull(e.target.value); compareCarriers(); });
    q('courier-shipments-ftl-list')?.addEventListener('change', (e) => { if (!e.target.classList.contains('ship-ftl-box')) return; const id = intOrNull(e.target.value); if (!id) return; e.target.checked ? s.selShipFtl.add(id) : s.selShipFtl.delete(id); renderShipFtl(); });
    q('courier-warehouse-list')?.addEventListener('click', (e) => { const sid = e.target.getAttribute('data-wh-sync'); if (sid) return doSyncWh(intOrNull(sid)).catch((x) => toast(x.message, 'error')); const lid = e.target.getAttribute('data-wh-link'); if (lid) { const w = s.wh.find((x) => Number(x.id) === Number(lid)); if (!w) return; q('courier-warehouse-link-id').value = w.id; q('courier-warehouse-link-name').textContent = w.name || '-'; q('courier-warehouse-link-pickup').value = w.shipdaak_pickup_id || ''; q('courier-warehouse-link-rto').value = w.shipdaak_rto_id || ''; modal('courier-warehouse-link-modal', true); } });
    q('courier-ftl-source-city')?.addEventListener('change', () => { fillDestAndBoxes(); previewFtl(); });
    q('courier-ftl-destination-city')?.addEventListener('change', () => { fillDestAndBoxes(); previewFtl(); });
    q('courier-ftl-container-type')?.addEventListener('change', previewFtl);
  }

  async function init() {
    bind(); await Promise.all([loadWh(), loadRoutes()]);
    if (cfg.activeSection === 'orders') { updateCreateOrderButton(); setActive([...document.querySelectorAll('[data-orders-type]')], (x) => x.dataset.ordersType === 'b2c'); setActive([...document.querySelectorAll('[data-orders-status]')], (x) => x.dataset.ordersStatus === 'all'); await loadOrders(); }
    if (cfg.activeSection === 'shipments') { setActive([...document.querySelectorAll('[data-shipment-type]')], (x) => x.dataset.shipmentType === 'b2c'); await loadShipOrders(); }
    if (cfg.activeSection === 'warehouses') renderWh();
  }

  init().catch((e) => toast(e.message || 'Failed to initialize courier workspace.', 'error'));
})();







