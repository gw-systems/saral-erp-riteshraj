(() => {
  const cfg = window.courierFtlFormConfig;
  if (!cfg) return;

  const q = (id) => document.getElementById(id);
  const csrf = () => ((document.cookie.split(';').map((x) => x.trim()).find((x) => x.startsWith('csrftoken=')) || '').split('=').slice(1).join('='));
  const intOrNull = (value) => {
    const parsed = parseInt(value, 10);
    return Number.isInteger(parsed) ? parsed : null;
  };
  const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(value || 0));
  const state = { routes: {} };

  function showError(message) {
    const el = q('courier-ftl-alert');
    if (!el) return;
    el.textContent = message || 'Something went wrong while saving the FTL order.';
    el.classList.add('is-visible');
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function clearError() {
    const el = q('courier-ftl-alert');
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

  function optionMarkup(items, selectedValue, placeholder) {
    const rows = [`<option value="">${placeholder}</option>`];
    items.forEach((item) => {
      const selected = item === selectedValue ? ' selected' : '';
      rows.push(`<option value="${String(item).replace(/"/g, '&quot;')}"${selected}>${item}</option>`);
    });
    return rows.join('');
  }

  function renderRoutes() {
    const source = q('source_city');
    const destination = q('destination_city');
    const container = q('container_type');
    if (!source || !destination || !container) return;

    const sourceCity = source.value || cfg.initialSourceCity || '';
    source.innerHTML = optionMarkup(Object.keys(state.routes).sort(), sourceCity, 'Select source city');
    if (sourceCity) source.value = sourceCity;

    const destinationCities = source.value && state.routes[source.value] ? Object.keys(state.routes[source.value]).sort() : [];
    const selectedDestination = destinationCities.includes(cfg.initialDestinationCity) && !destination.value ? cfg.initialDestinationCity : destination.value;
    destination.innerHTML = optionMarkup(destinationCities, selectedDestination, 'Select destination city');
    if (selectedDestination) destination.value = selectedDestination;

    const containers = source.value && destination.value && state.routes[source.value]?.[destination.value]
      ? state.routes[source.value][destination.value]
      : [];
    const selectedContainer = containers.includes(cfg.initialContainerType) && !container.value ? cfg.initialContainerType : container.value;
    container.innerHTML = optionMarkup(containers, selectedContainer, 'Select container type');
    if (selectedContainer) container.value = selectedContainer;
  }

  async function loadRoutes() {
    state.routes = await api(cfg.ftlRoutesUrl);
    renderRoutes();
    previewPrice();
  }

  function setPreviewHidden(hidden) {
    q('courier-ftl-preview-empty').hidden = !hidden;
    q('courier-ftl-preview').hidden = hidden;
  }

  async function previewPrice() {
    const sourceCity = q('source_city')?.value;
    const destinationCity = q('destination_city')?.value;
    const containerType = q('container_type')?.value;
    if (!sourceCity || !destinationCity || !containerType) {
      setPreviewHidden(true);
      return;
    }
    try {
      const response = await api(cfg.ftlRateUrl, {
        method: 'POST',
        body: {
          source_city: sourceCity,
          destination_city: destinationCity,
          container_type: containerType,
        },
      });
      q('courier-ftl-preview-base').textContent = money(response.base_price);
      q('courier-ftl-preview-escalation').textContent = money(response.escalation_amount);
      q('courier-ftl-preview-gst').textContent = money(response.gst_amount);
      q('courier-ftl-preview-total').textContent = money(response.total_price);
      setPreviewHidden(false);
    } catch {
      setPreviewHidden(true);
    }
  }

  function buildPayload() {
    return {
      name: q('ftl_name').value.trim(),
      phone: q('ftl_phone').value.trim(),
      email: q('ftl_email').value.trim(),
      source_city: q('source_city').value,
      source_pincode: intOrNull(q('source_pincode').value),
      source_address: q('source_address').value.trim(),
      destination_city: q('destination_city').value,
      destination_pincode: intOrNull(q('destination_pincode').value),
      destination_address: q('destination_address').value.trim(),
      container_type: q('container_type').value,
      notes: q('ftl_notes').value.trim(),
    };
  }

  function redirectWithFlash() {
    const nextUrl = new URL(cfg.redirectUrl, window.location.origin);
    nextUrl.searchParams.set('type', 'ftl');
    nextUrl.searchParams.set('flash', cfg.formMode === 'edit' ? 'updated' : 'created');
    window.location.assign(nextUrl.toString());
  }

  async function handleSubmit(event) {
    event.preventDefault();
    clearError();
    const form = q('courier-ftl-page-form');
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
    q('courier-ftl-page-form')?.addEventListener('submit', handleSubmit);
    q('source_city')?.addEventListener('change', () => {
      cfg.initialDestinationCity = '';
      cfg.initialContainerType = '';
      renderRoutes();
      previewPrice();
    });
    q('destination_city')?.addEventListener('change', () => {
      cfg.initialContainerType = '';
      renderRoutes();
      previewPrice();
    });
    q('container_type')?.addEventListener('change', previewPrice);
  }

  bind();
  loadRoutes().catch((error) => showError(error.message));
})();
