(() => {
  const cfg = window.courierOrderFormConfig;
  if (!cfg) return;

  const q = (id) => document.getElementById(id);
  const csrf = () => ((document.cookie.split(';').map((x) => x.trim()).find((x) => x.startsWith('csrftoken=')) || '').split('=').slice(1).join('='));
  const num = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0);
  const intOrNull = (value) => {
    const parsed = parseInt(value, 10);
    return Number.isInteger(parsed) ? parsed : null;
  };

  function showError(message) {
    const el = q('courier-form-alert');
    if (!el) return;
    el.textContent = message || 'Something went wrong while saving the order.';
    el.classList.add('is-visible');
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function clearError() {
    const el = q('courier-form-alert');
    if (!el) return;
    el.textContent = '';
    el.classList.remove('is-visible');
  }

  function formatError(payload, status) {
    if (!payload) return `Request failed (${status})`;
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail;
    const parts = Object.entries(payload)
      .map(([key, value]) => {
        const rendered = Array.isArray(value) ? value.join(', ') : (typeof value === 'string' ? value : JSON.stringify(value));
        return `${key}: ${rendered}`;
      })
      .filter(Boolean);
    return parts.length ? parts.join(' | ') : `Request failed (${status})`;
  }

  async function api(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set('Accept', 'application/json');
    if (options.body) {
      headers.set('Content-Type', 'application/json');
      options.body = JSON.stringify(options.body);
    }
    if ((options.method || 'GET').toUpperCase() !== 'GET') headers.set('X-CSRFToken', csrf());
    const response = await fetch(url, { ...options, headers });
    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = { detail: text };
    }
    if (!response.ok) throw new Error(formatError(payload, response.status));
    return payload;
  }

  function setGeo(city = '', state = '') {
    const cityEl = q('recipient_city');
    const stateEl = q('recipient_state');
    if (cityEl) cityEl.value = city || '';
    if (stateEl) stateEl.value = state || '';
  }

  async function lookupPin() {
    const pin = String(q('recipient_pincode')?.value || '').trim();
    if (!/^\d{6}$/.test(pin)) {
      setGeo('', '');
      return;
    }
    try {
      const response = await api(String(cfg.lookupPincodeUrlTemplate).replace('111111', pin));
      setGeo(response.city || '', response.state || '');
    } catch {
      setGeo('', '');
    }
  }

  function buildPayload() {
    return {
      recipient_name: q('recipient_name').value.trim(),
      recipient_contact: q('recipient_contact').value.trim(),
      recipient_address: q('recipient_address').value.trim(),
      recipient_pincode: intOrNull(q('recipient_pincode').value),
      recipient_city: q('recipient_city').value.trim(),
      recipient_state: q('recipient_state').value.trim(),
      recipient_email: q('recipient_email').value.trim(),
      sender_pincode: intOrNull(q('sender_pincode').value),
      sender_name: q('sender_name').value.trim(),
      sender_address: q('sender_address').value.trim(),
      sender_phone: q('sender_phone').value.trim(),
      weight: num(q('weight').value),
      length: num(q('length').value),
      width: num(q('width').value),
      height: num(q('height').value),
      payment_mode: q('payment_mode').value,
      order_value: num(q('order_value').value),
      item_type: q('item_type').value.trim(),
      sku: q('sku').value.trim(),
      quantity: intOrNull(q('quantity').value) || 1,
      item_amount: num(q('item_amount').value),
      warehouse: intOrNull(q('warehouse').value),
      notes: q('notes').value.trim(),
    };
  }

  function redirectWithFlash() {
    const nextUrl = new URL(cfg.redirectUrl, window.location.origin);
    nextUrl.searchParams.set('type', cfg.orderType);
    nextUrl.searchParams.set('flash', cfg.formMode === 'edit' ? 'updated' : 'created');
    window.location.assign(nextUrl.toString());
  }

  async function handleSubmit(event) {
    event.preventDefault();
    clearError();
    const form = q('courier-order-page-form');
    if (form && !form.reportValidity()) {
      const invalid = form.querySelector(':invalid');
      invalid?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      invalid?.focus({ preventScroll: true });
      return;
    }
    const submit = form?.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      await api(cfg.apiUrl, {
        method: cfg.formMode === 'edit' ? 'PATCH' : 'POST',
        body: buildPayload(),
      });
      redirectWithFlash();
    } catch (error) {
      showError(error.message);
    } finally {
      if (submit) submit.disabled = false;
    }
  }

  function bind() {
    q('courier-order-page-form')?.addEventListener('submit', handleSubmit);
    q('recipient_pincode')?.addEventListener('input', () => {
      const pin = String(q('recipient_pincode')?.value || '').trim();
      if (/^\d{6}$/.test(pin)) lookupPin();
      else setGeo('', '');
    });
    q('recipient_pincode')?.addEventListener('blur', lookupPin);
  }

  bind();
  if (String(q('recipient_pincode')?.value || '').trim().length === 6) lookupPin();
})();
