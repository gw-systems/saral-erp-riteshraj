(function () {
    const config = window.courierCalculatorConfig;
    if (!config) {
        return;
    }

    const VOLUMETRIC_DIVISOR = 5000;
    const BOX_DEFAULT = () => ({
        id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
        weight: "",
        length: "",
        width: "",
        height: "",
        value: "",
    });
    const BREAKDOWN_FIELDS = [
        ["base_transport_cost", "Base Transport"],
        ["docket_fee", "Docket Fee"],
        ["eway_bill_fee", "E-Way Bill Fee"],
        ["fuel_surcharge", "Fuel Surcharge"],
        ["hamali_charge", "Hamali"],
        ["pickup_charge", "Pickup"],
        ["delivery_charge", "Delivery"],
        ["fod_charge", "FOD"],
        ["dod_charge", "DOD"],
        ["risk_charge", "Risk"],
        ["fov_charge", "FOV"],
        ["ecc_charge", "ECC"],
        ["cod_charge", "COD"],
        ["profit_margin", "Escalation"],
        ["gst_amount", "GST"],
        ["final_total", "Total"],
    ];

    let currentMode = "b2c";
    let boxes = [BOX_DEFAULT()];
    let dimensionUnit = "cm";
    let currentRates = [];
    let ftlRoutes = {};
    let rateCardOptions = {
        b2c: { loaded: false, items: [], selected: [] },
        b2b: { loaded: false, items: [], selected: [] },
    };

    const els = {};

    function byId(id) {
        return document.getElementById(id);
    }

    function cacheElements() {
        els.alert = byId("courier-alert");
        els.tabs = Array.from(document.querySelectorAll("[data-calc-tab]"));
        els.regularPanel = byId("courier-regular-panel");
        els.ftlPanel = byId("courier-ftl-panel");
        els.regularResultsPanel = byId("courier-regular-results-panel");
        els.ftlResultsPanel = byId("courier-ftl-results-panel");
        els.regularResults = byId("courier-regular-results");
        els.ftlResults = byId("courier-ftl-results");
        els.regularForm = byId("courier-regular-form");
        els.ftlForm = byId("courier-ftl-form");
        els.sourcePincode = byId("courier-source-pincode");
        els.destPincode = byId("courier-dest-pincode");
        els.categoryFilter = byId("courier-category-filter");
        els.dimensionUnit = byId("courier-dimension-unit");
        els.paymentMode = byId("courier-payment-mode");
        els.totalOrderValue = byId("courier-total-order-value");
        els.totalApplicableWeight = byId("courier-total-applicable-weight");
        els.boxList = byId("courier-box-list");
        els.addBoxButton = byId("courier-add-box");
        els.ftlSource = byId("courier-ftl-source");
        els.ftlDestination = byId("courier-ftl-destination");
        els.ftlTruckType = byId("courier-ftl-truck-type");
        els.rateCardTrigger = byId("courier-ratecard-trigger");
        els.rateCardDropdown = byId("courier-ratecard-dropdown");
        els.rateCardPicker = byId("courier-ratecard-picker");
        els.rateCardOptionList = byId("courier-ratecard-option-list");
        els.rateCardDownload = byId("courier-ratecard-download");
        els.selectAllFamilies = byId("courier-ratecard-select-all");
        els.clearAllFamilies = byId("courier-ratecard-clear-all");
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function numberOrZero(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function formatMoney(value) {
        return new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 2,
        }).format(numberOrZero(value));
    }

    function showAlert(message, type) {
        if (!els.alert) {
            return;
        }
        const styles = {
            info: "border-blue-200 bg-blue-50 text-blue-800",
            success: "border-emerald-200 bg-emerald-50 text-emerald-800",
            error: "border-red-200 bg-red-50 text-red-800",
        };
        els.alert.className = `rounded-xl border px-4 py-3 text-sm ${styles[type] || styles.info}`;
        els.alert.textContent = message;
        els.alert.classList.remove("hidden");
    }

    function hideAlert() {
        els.alert?.classList.add("hidden");
    }
    function clearFieldInvalid(input) {
        if (!input) {
            return;
        }
        input.classList.remove("is-invalid");
        input.closest(".courier-calc-field")?.classList.remove("is-invalid");
    }

    function markFieldInvalid(input) {
        if (!input) {
            return;
        }
        input.classList.add("is-invalid");
        input.closest(".courier-calc-field")?.classList.add("is-invalid");
    }

    function getBoxInput(boxId, field) {
        return els.boxList?.querySelector(`[data-box-id="${boxId}"][data-box-field="${field}"]`);
    }

    function clearBoxValidation() {
        els.boxList?.querySelectorAll(".courier-calc-input.is-invalid").forEach((input) => input.classList.remove("is-invalid"));
        els.boxList?.querySelectorAll(".courier-calc-field.is-invalid").forEach((field) => field.classList.remove("is-invalid"));
    }

    function convertToCm(value) {
        const numeric = numberOrZero(value);
        const map = { cm: 1, mm: 0.1, m: 100, in: 2.54, ft: 30.48 };
        return numeric * (map[dimensionUnit] || 1);
    }

    function inferCategory(rate) {
        const explicit = String(rate?.service_category || "").trim();
        if (explicit) {
            return explicit;
        }
        const carrierName = String(rate?.carrier || "").toLowerCase();
        if (carrierName.includes("ndd heavy")) return "NDD Heavy Surface";
        if (carrierName.includes("heavy")) return "Heavy Surface";
        if (carrierName.includes("documents")) return "Documents";
        if (carrierName.includes("rvp")) return "RVP";
        if (carrierName.includes("ndd")) return "NDD Surface";
        if (carrierName.includes("air")) return "Air";
        return "Surface";
    }

    function getBoxMetrics(box) {
        const actualWeight = numberOrZero(box.weight);
        const volumetricWeight = (
            convertToCm(box.length) *
            convertToCm(box.width) *
            convertToCm(box.height)
        ) / VOLUMETRIC_DIVISOR;
        const applicableWeight = Math.max(actualWeight, volumetricWeight);
        const value = numberOrZero(box.value);
        return { actualWeight, volumetricWeight, applicableWeight, value };
    }

    function syncTotals() {
        const totals = boxes.reduce((acc, box) => {
            const metrics = getBoxMetrics(box);
            acc.weight += metrics.applicableWeight;
            acc.value += metrics.value;
            return acc;
        }, { weight: 0, value: 0 });
        if (els.totalApplicableWeight) {
            els.totalApplicableWeight.textContent = `${totals.weight.toFixed(2)} kg`;
        }
        if (els.totalOrderValue) {
            els.totalOrderValue.value = totals.value.toFixed(2);
        }
    }
    function updateBoxMeta(boxId) {
        if (!els.boxList) {
            return;
        }
        const box = boxes.find((item) => item.id === boxId);
        if (!box) {
            return;
        }
        const container = els.boxList.querySelector(`[data-box-meta-id="${boxId}"]`);
        if (!container) {
            return;
        }
        const metrics = getBoxMetrics(box);
        container.innerHTML = `
            <span>Box Volumetric Weight: <strong>${metrics.volumetricWeight.toFixed(2)} kg</strong></span>
            <span>Box Applicable: <strong>${metrics.applicableWeight.toFixed(2)} kg</strong></span>
        `;
    }

    function renderBoxes() {
        if (!els.boxList) {
            return;
        }
        els.boxList.innerHTML = boxes.map((box, index) => {
            const metrics = getBoxMetrics(box);
            return `
                <div class="courier-calc-box">
                    <div class="courier-calc-box-head">
                        <span class="courier-calc-box-name">Box ${index + 1}</span>
                        ${boxes.length > 1 ? `<button type="button" class="courier-calc-dropdown-link" data-remove-box="${escapeHtml(box.id)}">Remove</button>` : ""}
                    </div>
                    <div class="courier-calc-box-grid">
                        <div class="courier-calc-field">
                            <label>Weight (kg)</label>
                            <input class="courier-calc-input" type="number" min="0.01" step="0.01" data-box-field="weight" data-box-id="${escapeHtml(box.id)}" value="${escapeHtml(box.weight)}" placeholder="0.00" required>
                        </div>
                        <div class="courier-calc-field">
                            <label>Length</label>
                            <input class="courier-calc-input" type="number" min="0.1" step="0.01" data-box-field="length" data-box-id="${escapeHtml(box.id)}" value="${escapeHtml(box.length)}" placeholder="Length" required>
                        </div>
                        <div class="courier-calc-field">
                            <label>Width</label>
                            <input class="courier-calc-input" type="number" min="0.1" step="0.01" data-box-field="width" data-box-id="${escapeHtml(box.id)}" value="${escapeHtml(box.width)}" placeholder="Width" required>
                        </div>
                        <div class="courier-calc-field">
                            <label>Height</label>
                            <input class="courier-calc-input" type="number" min="0.1" step="0.01" data-box-field="height" data-box-id="${escapeHtml(box.id)}" value="${escapeHtml(box.height)}" placeholder="Height" required>
                        </div>
                        <div class="courier-calc-field">
                            <label>Value (opt)</label>
                            <input class="courier-calc-input" type="number" min="0" step="0.01" data-box-field="value" data-box-id="${escapeHtml(box.id)}" value="${escapeHtml(box.value)}" placeholder="0">
                        </div>
                    </div>
                    <div class="courier-calc-box-meta" data-box-meta-id="${escapeHtml(box.id)}">
                        <span>Box Volumetric Weight: <strong>${metrics.volumetricWeight.toFixed(2)} kg</strong></span>
                        <span>Box Applicable: <strong>${metrics.applicableWeight.toFixed(2)} kg</strong></span>
                    </div>
                </div>
            `;
        }).join("");
        syncTotals();
    }

    function renderRegularResults(results) {
        if (!els.regularResults) {
            return;
        }
        const selectedCategory = els.categoryFilter?.value || "all";
        const items = (Array.isArray(results) ? results : []).filter((rate) => {
            if (selectedCategory === "all") {
                return true;
            }
            return inferCategory(rate) === selectedCategory;
        });
        if (!items.length) {
            const message = currentRates.length ? "No carriers match the selected category." : "No serviceable carriers matched this route.";
            els.regularResults.innerHTML = `<div class="courier-calc-empty">${escapeHtml(message)}</div>`;
            return;
        }
        els.regularResults.innerHTML = items.map((rate, index) => {
            const breakdownId = `courier-breakdown-${index}`;
            const breakdown = rate?.breakdown && typeof rate.breakdown === "object" ? rate.breakdown : {};
            const breakdownRows = BREAKDOWN_FIELDS.map(([key, label]) => {
                const value = breakdown[key];
                if (value === undefined || value === null || value === "") {
                    return "";
                }
                if (numberOrZero(value) === 0 && !["base_transport_cost", "profit_margin", "gst_amount", "final_total"].includes(key)) {
                    return "";
                }
                return `<div class="courier-calc-breakdown-row"><span>${escapeHtml(label)}</span><strong>${formatMoney(value)}</strong></div>`;
            }).filter(Boolean).join("");
            const zone = rate?.zone || rate?.applied_zone || "-";
            return `
                <div class="courier-calc-result-card">
                    <button type="button" class="courier-calc-result-summary" data-breakdown-toggle="${breakdownId}">
                        <div>
                            <div class="courier-calc-result-name">${escapeHtml(rate?.carrier || "Carrier")}</div>
                            <div class="courier-calc-result-meta">${escapeHtml(rate?.mode || "Mode")} â€¢ ${escapeHtml(zone)}</div>
                            <div class="courier-calc-pill-row">
                                <span class="courier-calc-pill">${escapeHtml(inferCategory(rate))}</span>
                                <span class="courier-calc-pill">${escapeHtml(currentMode.toUpperCase())}</span>
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div class="courier-calc-result-cost">${formatMoney(rate?.total_cost)}</div>
                            <div class="courier-calc-result-meta">Click for breakdown</div>
                            <div class="courier-calc-result-chevron">?</div>
                        </div>
                    </button>
                    <div id="${breakdownId}" class="courier-calc-breakdown courier-calc-hidden">
                        <div class="courier-calc-breakdown-grid">
                            ${breakdownRows}
                        </div>
                    </div>
                </div>
            `;
        }).join("");
    }

    function renderFtlPlaceholder() {
        if (els.ftlResults) {
            els.ftlResults.innerHTML = '<div class="courier-calc-empty">Choose an FTL route and calculate the price to see the result here.</div>';
        }
    }

    function renderFtlResult(result) {
        if (!els.ftlResults) {
            return;
        }
        els.ftlResults.innerHTML = `
            <div class="courier-calc-ftl-grid">
                <div class="courier-calc-ftl-card">
                    <div class="courier-calc-ftl-label">Base Price</div>
                    <div class="courier-calc-ftl-value">${formatMoney(result.base_price)}</div>
                </div>
                <div class="courier-calc-ftl-card">
                    <div class="courier-calc-ftl-label">Base With Escalation</div>
                    <div class="courier-calc-ftl-value">${formatMoney(result.price_with_escalation)}</div>
                </div>
                <div class="courier-calc-ftl-card">
                    <div class="courier-calc-ftl-label">GST</div>
                    <div class="courier-calc-ftl-value">${formatMoney(result.gst_amount)}</div>
                </div>
                <div class="courier-calc-ftl-card">
                    <div class="courier-calc-ftl-label">Escalation Amount</div>
                    <div class="courier-calc-ftl-value">${formatMoney(result.escalation_amount)}</div>
                </div>
                <div class="courier-calc-ftl-card">
                    <div class="courier-calc-ftl-label">Route</div>
                    <div class="courier-calc-ftl-value">${escapeHtml(result.source_city)} to ${escapeHtml(result.destination_city)}</div>
                </div>
                <div class="courier-calc-ftl-card">
                    <div class="courier-calc-ftl-label">Total Cost</div>
                    <div class="courier-calc-ftl-value">${formatMoney(result.total_price)}</div>
                </div>
            </div>
        `;
    }

    function validatePincode(value, label) {
        if (!/^\d{6}$/.test(String(value || "").trim())) {
            throw new Error(`${label} must be a valid 6-digit pincode.`);
        }
        return Number(value);
    }

    function buildOrdersPayload() {
        clearBoxValidation();
        let firstInvalidInput = null;

        const orders = boxes.map((box) => {
            const weight = numberOrZero(box.weight);
            const length = convertToCm(box.length);
            const width = convertToCm(box.width);
            const height = convertToCm(box.height);

            [
                ["weight", weight],
                ["length", length],
                ["width", width],
                ["height", height],
            ].forEach(([field, value]) => {
                if (value > 0) {
                    return;
                }
                const input = getBoxInput(box.id, field);
                markFieldInvalid(input);
                if (!firstInvalidInput) {
                    firstInvalidInput = input;
                }
            });

            return { weight, length, width, height };
        });

        if (firstInvalidInput) {
            firstInvalidInput.focus();
            throw new Error("Fill all required box fields: weight, length, width, and height.");
        }

        return orders;
    }

    async function readJson(response) {
        try {
            return await response.json();
        } catch (error) {
            return null;
        }
    }

    async function submitRegularCalculator(event) {
        event.preventDefault();
        hideAlert();
        try {
            const payload = {
                source_pincode: validatePincode(els.sourcePincode?.value, "Source pincode"),
                dest_pincode: validatePincode(els.destPincode?.value, "Destination pincode"),
                orders: buildOrdersPayload(),
                mode: "Both",
                business_type: currentMode,
                is_cod: els.paymentMode?.value === "COD",
                order_value: numberOrZero(els.totalOrderValue?.value),
            };
            const response = await fetch(config.compareRatesUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify(payload),
            });
            const body = await readJson(response);
            if (!response.ok) {
                throw new Error(body?.detail || "Rate comparison failed.");
            }
            currentRates = Array.isArray(body) ? body.slice().sort((a, b) => numberOrZero(a.total_cost) - numberOrZero(b.total_cost)) : [];
            renderRegularResults(currentRates);
            showAlert("Rate comparison completed.", "success");
        } catch (error) {
            currentRates = [];
            renderRegularResults([]);
            showAlert(error.message, "error");
        }
    }

    async function loadFtlRoutes() {
        try {
            const response = await fetch(config.ftlRoutesUrl, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const body = await readJson(response);
            if (!response.ok) {
                throw new Error(body?.detail || "Unable to load FTL routes.");
            }
            ftlRoutes = body || {};
            populateSelect(els.ftlSource, Object.keys(ftlRoutes).sort(), "Select source city");
            populateSelect(els.ftlDestination, [], "Select destination city");
            populateSelect(els.ftlTruckType, [], "Select truck type");
        } catch (error) {
            showAlert(error.message, "error");
        }
    }

    function populateSelect(select, items, placeholder) {
        if (!select) {
            return;
        }
        const options = [`<option value="">${escapeHtml(placeholder)}</option>`]
            .concat(items.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`));
        select.innerHTML = options.join("");
    }

    function updateFtlDestinations() {
        const source = els.ftlSource?.value;
        const destinations = source && ftlRoutes[source] ? Object.keys(ftlRoutes[source]).sort() : [];
        populateSelect(els.ftlDestination, destinations, "Select destination city");
        populateSelect(els.ftlTruckType, [], "Select truck type");
    }

    function updateFtlTruckTypes() {
        const source = els.ftlSource?.value;
        const destination = els.ftlDestination?.value;
        const trucks = source && destination && ftlRoutes[source]?.[destination] ? ftlRoutes[source][destination].slice().sort() : [];
        populateSelect(els.ftlTruckType, trucks, "Select truck type");
    }

    async function submitFtlCalculator(event) {
        event.preventDefault();
        hideAlert();
        try {
            const source_city = els.ftlSource?.value;
            const destination_city = els.ftlDestination?.value;
            const container_type = els.ftlTruckType?.value;
            if (!source_city || !destination_city || !container_type) {
                throw new Error("Choose source city, destination city, and truck type.");
            }
            const response = await fetch(config.ftlRateUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify({ source_city, destination_city, container_type }),
            });
            const body = await readJson(response);
            if (!response.ok) {
                throw new Error(body?.detail || "FTL rate calculation failed.");
            }
            renderFtlResult(body);
            showAlert("FTL rate calculated.", "success");
        } catch (error) {
            renderFtlPlaceholder();
            showAlert(error.message, "error");
        }
    }

    function currentRateCardState() {
        return currentMode === "b2b" ? rateCardOptions.b2b : rateCardOptions.b2c;
    }

    function currentRateCardOptionsUrl() {
        return currentMode === "b2b" ? config.b2bRateCardOptionsUrl : config.b2cRateCardOptionsUrl;
    }

    function currentRateCardDownloadUrl() {
        if (currentMode === "ftl") {
            return config.ftlRateCardUrl;
        }
        return currentMode === "b2b" ? config.b2bRateCardUrl : config.b2cRateCardUrl;
    }

    function updateRateCardTriggerLabel() {
        if (!els.rateCardTrigger || currentMode === "ftl") {
            return;
        }
        const state = currentRateCardState();
        if (!state.loaded) {
            els.rateCardTrigger.textContent = "Loading couriers...";
            els.rateCardTrigger.disabled = true;
            return;
        }
        els.rateCardTrigger.disabled = false;
        if (!state.items.length) {
            els.rateCardTrigger.textContent = "No couriers available";
            return;
        }
        if (state.selected.length === state.items.length) {
            els.rateCardTrigger.textContent = "All couriers";
            return;
        }
        if (!state.selected.length) {
            els.rateCardTrigger.textContent = "Select couriers";
            return;
        }
        const selectedRow = state.items.find((item) => item.key === state.selected[0]);
        els.rateCardTrigger.textContent = state.selected.length === 1
            ? (selectedRow?.label || state.selected[0])
            : `${state.selected.length} couriers selected`;
    }

    function renderRateCardOptions() {
        if (!els.rateCardOptionList || currentMode === "ftl") {
            return;
        }
        const state = currentRateCardState();
        if (!state.loaded) {
            els.rateCardOptionList.innerHTML = '<div class="courier-calc-empty">Loading families...</div>';
            return;
        }
        if (!state.items.length) {
            els.rateCardOptionList.innerHTML = '<div class="courier-calc-empty">No families available for this rate card.</div>';
            return;
        }
        els.rateCardOptionList.innerHTML = state.items.map((item) => {
            const checked = state.selected.includes(item.key) ? "checked" : "";
            return `
                <label class="courier-calc-option">
                    <input type="checkbox" data-ratecard-family="${escapeHtml(item.key)}" ${checked}>
                    <span>
                        <span class="courier-calc-option-name">${escapeHtml(item.label)}</span>
                        <span class="courier-calc-option-count">${escapeHtml(item.carrier_count)} carrier${Number(item.carrier_count) === 1 ? "" : "s"}</span>
                    </span>
                </label>
            `;
        }).join("");
    }

    async function ensureRateCardOptionsLoaded() {
        if (currentMode === "ftl") {
            return;
        }
        const state = currentRateCardState();
        if (state.loaded) {
            renderRateCardOptions();
            updateRateCardTriggerLabel();
            return;
        }
        renderRateCardOptions();
        try {
            const response = await fetch(currentRateCardOptionsUrl(), {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const body = await readJson(response);
            if (!response.ok) {
                throw new Error(body?.detail || "Unable to load rate-card families.");
            }
            state.loaded = true;
            state.items = Array.isArray(body?.carriers) ? body.carriers : [];
            state.selected = state.items.map((item) => item.key);
            renderRateCardOptions();
            updateRateCardTriggerLabel();
        } catch (error) {
            state.loaded = true;
            state.items = [];
            state.selected = [];
            renderRateCardOptions();
            updateRateCardTriggerLabel();
            showAlert(error.message, "error");
        }
    }

    function closeRateCardDropdown() {
        els.rateCardDropdown?.classList.add("is-hidden");
    }

    function updateRateCardControls() {
        const regularMode = currentMode !== "ftl";
        els.rateCardPicker?.classList.toggle("courier-calc-hidden", !regularMode);
        if (els.rateCardDownload) {
            els.rateCardDownload.textContent = currentMode === "ftl" ? "FTL Rate Card" : currentMode === "b2b" ? "B2B Rate Card" : "B2C Rate Card";
        }
        if (!regularMode) {
            closeRateCardDropdown();
            return;
        }
        updateRateCardTriggerLabel();
        ensureRateCardOptionsLoaded();
    }

    async function downloadRateCard() {
        hideAlert();
        try {
            const url = new URL(currentRateCardDownloadUrl(), window.location.origin);
            if (currentMode !== "ftl") {
                const state = currentRateCardState();
                if (!state.selected.length) {
                    throw new Error("Select at least one courier family for the rate card.");
                }
                if (state.selected.length !== state.items.length) {
                    state.selected.forEach((name) => url.searchParams.append("carrier", name));
                }
            }
            const response = await fetch(url.toString(), {
                credentials: "same-origin",
                headers: { Accept: "application/pdf,application/json" },
            });
            if (!response.ok) {
                const body = await readJson(response);
                throw new Error(body?.detail || "Rate-card download failed.");
            }
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const opened = window.open(objectUrl, "_blank", "noopener");
            if (!opened) {
                throw new Error("Popup blocked. Allow popups to view the rate card.");
            }
            window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
            showAlert("Rate card opened in a new tab.", "success");
        } catch (error) {
            showAlert(error.message, "error");
        }
    }

    function resetRegularState() {
        boxes = [BOX_DEFAULT()];
        currentRates = [];
        els.regularForm?.reset();
        if (els.dimensionUnit) {
            els.dimensionUnit.value = "cm";
        }
        if (els.categoryFilter) {
            els.categoryFilter.value = "all";
        }
        if (els.paymentMode) {
            els.paymentMode.value = "Prepaid";
        }
        dimensionUnit = "cm";
        renderBoxes();
        renderRegularResults([]);
    }

    function setMode(mode) {
        currentMode = mode;
        els.tabs.forEach((tab) => {
            const active = tab.dataset.calcTab === mode;
            tab.classList.toggle("is-active", active);
            tab.setAttribute("aria-pressed", active ? "true" : "false");
        });
        const regularMode = mode !== "ftl";
        els.regularPanel?.classList.toggle("courier-calc-hidden", !regularMode);
        els.regularResultsPanel?.classList.toggle("courier-calc-hidden", !regularMode);
        els.ftlPanel?.classList.toggle("courier-calc-hidden", regularMode);
        els.ftlResultsPanel?.classList.toggle("courier-calc-hidden", regularMode);
        updateRateCardControls();
        hideAlert();
        if (regularMode) {
            resetRegularState();
        } else {
            renderFtlPlaceholder();
            if (!Object.keys(ftlRoutes).length) {
                loadFtlRoutes();
            }
        }
    }

    function bindEvents() {
        els.tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.calcTab)));
        els.addBoxButton?.addEventListener("click", () => {
            boxes = boxes.concat([BOX_DEFAULT()]);
            renderBoxes();
        });
        els.boxList?.addEventListener("input", (event) => {
            const field = event.target?.dataset?.boxField;
            const boxId = event.target?.dataset?.boxId;
            if (!field || !boxId) {
                return;
            }
            boxes = boxes.map((box) => box.id === boxId ? { ...box, [field]: event.target.value } : box);
            clearFieldInvalid(event.target);
            updateBoxMeta(boxId);
            syncTotals();
        });
        els.boxList?.addEventListener("click", (event) => {
            const boxId = event.target?.dataset?.removeBox;
            if (!boxId) {
                return;
            }
            boxes = boxes.filter((box) => box.id !== boxId);
            renderBoxes();
        });
        els.categoryFilter?.addEventListener("change", () => renderRegularResults(currentRates));
        els.dimensionUnit?.addEventListener("change", (event) => {
            dimensionUnit = event.target.value || "cm";
            renderBoxes();
        });
        els.regularForm?.addEventListener("submit", submitRegularCalculator);
        els.ftlForm?.addEventListener("submit", submitFtlCalculator);
        els.ftlSource?.addEventListener("change", updateFtlDestinations);
        els.ftlDestination?.addEventListener("change", updateFtlTruckTypes);
        els.rateCardTrigger?.addEventListener("click", () => {
            if (currentMode === "ftl") {
                return;
            }
            if (els.rateCardDropdown?.classList.contains("is-hidden")) {
                renderRateCardOptions();
                els.rateCardDropdown.classList.remove("is-hidden");
            } else {
                closeRateCardDropdown();
            }
        });
        els.rateCardDownload?.addEventListener("click", downloadRateCard);
        els.selectAllFamilies?.addEventListener("click", () => {
            const state = currentRateCardState();
            state.selected = state.items.map((item) => item.key);
            renderRateCardOptions();
            updateRateCardTriggerLabel();
        });
        els.clearAllFamilies?.addEventListener("click", () => {
            const state = currentRateCardState();
            state.selected = [];
            renderRateCardOptions();
            updateRateCardTriggerLabel();
        });
        els.rateCardOptionList?.addEventListener("change", (event) => {
            const family = event.target?.dataset?.ratecardFamily;
            if (!family) {
                return;
            }
            const state = currentRateCardState();
            if (event.target.checked) {
                if (!state.selected.includes(family)) {
                    state.selected.push(family);
                }
            } else {
                state.selected = state.selected.filter((item) => item !== family);
            }
            updateRateCardTriggerLabel();
        });
        els.regularResults?.addEventListener("click", (event) => {
            const target = event.target.closest("[data-breakdown-toggle]");
            if (!target) {
                return;
            }
            byId(target.dataset.breakdownToggle)?.classList.toggle("courier-calc-hidden");
        });
        document.addEventListener("click", (event) => {
            if (!els.rateCardPicker?.contains(event.target)) {
                closeRateCardDropdown();
            }
        });
    }

    function init() {
        cacheElements();
        if (!els.regularForm) {
            return;
        }
        bindEvents();
        renderBoxes();
        renderRegularResults([]);
        renderFtlPlaceholder();
        updateRateCardControls();
    }

    document.addEventListener("DOMContentLoaded", init);
}());









