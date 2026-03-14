/**
 * TallySync Common Utilities
 * Shared functions for all TallySync dashboards
 * Version: 1.0
 */

const TallySyncCommon = (function() {
    'use strict';

    // ============================================
    // CONFIGURATION
    // ============================================
    
    const API_BASE = '/tallysync/api/';
    const CHART_COLORS = {
        primary: '#3b82f6',
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#06b6d4',
        purple: '#8b5cf6',
        gray: '#6b7280'
    };

    // Store chart instances to prevent memory leaks
    const chartInstances = {};

    // ============================================
    // API UTILITIES
    // ============================================

    /**
     * Make API call with error handling
     * @param {string} endpoint - API endpoint (e.g., 'executive-summary')
     * @param {Object} params - Query parameters
     * @returns {Promise<Object>} - JSON response
     */
    async function apiCall(endpoint, params = {}) {
        try {
            // Build URL with query parameters — ensure trailing slash for Django
            const path = API_BASE + endpoint.replace(/\/+$/, '') + '/';
            const url = new URL(path, window.location.origin);
            Object.keys(params).forEach(key => {
                if (params[key] !== null && params[key] !== undefined && params[key] !== '') {
                    url.searchParams.append(key, params[key]);
                }
            });

            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;

        } catch (error) {
            console.error('API Error:', error);
            showError(`Failed to load data: ${error.message}`);
            throw error;
        }
    }

    /**
     * Get current filter values from form
     * @param {string} formId - ID of filter form
     * @returns {Object} - Filter parameters
     */
    function getFilters(formId = 'filterForm') {
        const form = document.getElementById(formId);
        if (!form) return {};

        return {
            start_date: form.querySelector('[name="start_date"]')?.value || '',
            end_date: form.querySelector('[name="end_date"]')?.value || '',
            company_id: form.querySelector('[name="company_id"]')?.value || '',
            month: form.querySelector('[name="month"]')?.value || '',
            year: form.querySelector('[name="year"]')?.value || ''
        };
    }

    // ============================================
    // UI UTILITIES
    // ============================================

    /**
     * Show loading state for an element
     * @param {string} elementId - Element ID
     * @param {boolean} isLoading - Loading state
     */
    function setLoading(elementId, isLoading) {
        const element = document.getElementById(elementId);
        if (!element) return;

        if (isLoading) {
            element.innerHTML = `
                <div class="flex items-center justify-center py-8">
                    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                </div>
            `;
        }
    }

    /**
     * Show error message
     * @param {string} message - Error message
     * @param {string} containerId - Optional container ID
     */
    function showError(message, containerId = null) {
        const errorHtml = `
            <div class="bg-red-50 border-l-4 border-red-400 p-4 mb-4">
                <div class="flex">
                    <div class="flex-shrink-0">
                        <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                        </svg>
                    </div>
                    <div class="ml-3">
                        <p class="text-sm text-red-700">${message}</p>
                    </div>
                </div>
            </div>
        `;

        if (containerId) {
            const container = document.getElementById(containerId);
            if (container) {
                container.innerHTML = errorHtml;
            }
        } else {
            // Show at top of page
            const alertContainer = document.getElementById('alertContainer');
            if (alertContainer) {
                alertContainer.innerHTML = errorHtml;
                setTimeout(() => {
                    alertContainer.innerHTML = '';
                }, 5000);
            }
        }
    }

    /**
     * Show success message
     * @param {string} message - Success message
     */
    function showSuccess(message) {
        const successHtml = `
            <div class="bg-green-50 border-l-4 border-green-400 p-4 mb-4">
                <div class="flex">
                    <div class="flex-shrink-0">
                        <svg class="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                        </svg>
                    </div>
                    <div class="ml-3">
                        <p class="text-sm text-green-700">${message}</p>
                    </div>
                </div>
            </div>
        `;

        const alertContainer = document.getElementById('alertContainer');
        if (alertContainer) {
            alertContainer.innerHTML = successHtml;
            setTimeout(() => {
                alertContainer.innerHTML = '';
            }, 3000);
        }
    }

    // ============================================
    // CHART UTILITIES
    // ============================================

    /**
     * Destroy existing chart instance to prevent memory leaks
     * @param {string} chartId - Chart canvas ID
     */
    function destroyChart(chartId) {
        if (chartInstances[chartId]) {
            chartInstances[chartId].destroy();
            delete chartInstances[chartId];
        }
    }

    /**
     * Create or update a Chart.js chart
     * @param {string} canvasId - Canvas element ID
     * @param {Object} config - Chart.js configuration
     * @returns {Chart} - Chart instance
     */
    function createChart(canvasId, config) {
        // Destroy existing chart
        destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element '${canvasId}' not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        if (!ctx) {
            console.error(`Could not get 2D context for '${canvasId}'`);
            return null;
        }

        try {
            const chart = new Chart(ctx, config);
            chartInstances[canvasId] = chart;
            return chart;
        } catch (error) {
            console.error(`Error creating chart '${canvasId}':`, error);
            return null;
        }
    }

    /**
     * Get default chart options
     * @param {Object} overrides - Options to override
     * @returns {Object} - Chart options
     */
    function getDefaultChartOptions(overrides = {}) {
        const defaults = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 15,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    titleFont: {
                        size: 14
                    },
                    bodyFont: {
                        size: 13
                    },
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            label += formatCurrency(context.parsed.y || context.parsed);
                            return label;
                        }
                    }
                }
            }
        };

        return deepMerge(defaults, overrides);
    }

    // ============================================
    // FORMATTING UTILITIES
    // ============================================

    /**
     * Format number as Indian currency (₹ with lakhs)
     * @param {number} amount - Amount to format
     * @returns {string} - Formatted currency
     */
    function formatCurrency(amount) {
        if (amount === null || amount === undefined) return '₹0';
        
        const num = parseFloat(amount);
        if (isNaN(num)) return '₹0';

        const abs = Math.abs(num);
        const sign = num < 0 ? '-' : '';

        // Format in Indian numbering system
        if (abs >= 10000000) {
            return sign + '₹' + (abs / 10000000).toFixed(2) + ' Cr';
        } else if (abs >= 100000) {
            return sign + '₹' + (abs / 100000).toFixed(2) + ' L';
        } else if (abs >= 1000) {
            return sign + '₹' + (abs / 1000).toFixed(2) + ' K';
        } else {
            return sign + '₹' + abs.toFixed(2);
        }
    }

    /**
     * Format number with commas (Indian style)
     * @param {number} num - Number to format
     * @returns {string} - Formatted number
     */
    function formatNumber(num) {
        if (num === null || num === undefined) return '0';
        
        const n = parseFloat(num);
        if (isNaN(n)) return '0';

        return n.toLocaleString('en-IN', {
            maximumFractionDigits: 2,
            minimumFractionDigits: 0
        });
    }

    /**
     * Format date string to readable format
     * @param {string} dateStr - ISO date string
     * @returns {string} - Formatted date
     */
    function formatDate(dateStr) {
        if (!dateStr) return '-';
        
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-IN', {
                day: '2-digit',
                month: 'short',
                year: 'numeric'
            });
        } catch (error) {
            return dateStr;
        }
    }

    /**
     * Format month from date string
     * @param {string} dateStr - ISO date string or datetime
     * @returns {string} - Formatted month (e.g., "Nov 2024")
     */
    function formatMonth(dateStr) {
        if (!dateStr) return '-';
        
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', {
                month: 'short',
                year: 'numeric'
            });
        } catch (error) {
            return dateStr;
        }
    }

    /**
     * Format percentage
     * @param {number} value - Percentage value
     * @returns {string} - Formatted percentage
     */
    function formatPercentage(value) {
        if (value === null || value === undefined) return '0%';
        
        const num = parseFloat(value);
        if (isNaN(num)) return '0%';

        return num.toFixed(2) + '%';
    }

    // ============================================
    // DATA UTILITIES
    // ============================================

    /**
     * Safely get nested property from object
     * @param {Object} obj - Object
     * @param {string} path - Property path (e.g., 'aging.0_30_days')
     * @param {*} defaultValue - Default value if not found
     * @returns {*} - Property value or default
     */
    function getNestedValue(obj, path, defaultValue = 0) {
        const keys = path.split('.');
        let value = obj;

        for (const key of keys) {
            if (value && typeof value === 'object' && key in value) {
                value = value[key];
            } else {
                return defaultValue;
            }
        }

        return value;
    }

    /**
     * Deep merge two objects
     * @param {Object} target - Target object
     * @param {Object} source - Source object
     * @returns {Object} - Merged object
     */
    function deepMerge(target, source) {
        const output = Object.assign({}, target);
        
        if (isObject(target) && isObject(source)) {
            Object.keys(source).forEach(key => {
                if (isObject(source[key])) {
                    if (!(key in target)) {
                        Object.assign(output, { [key]: source[key] });
                    } else {
                        output[key] = deepMerge(target[key], source[key]);
                    }
                } else {
                    Object.assign(output, { [key]: source[key] });
                }
            });
        }
        
        return output;
    }

    /**
     * Check if value is a plain object
     * @param {*} item - Value to check
     * @returns {boolean} - True if plain object
     */
    function isObject(item) {
        return item && typeof item === 'object' && !Array.isArray(item);
    }

    /**
     * Debounce function
     * @param {Function} func - Function to debounce
     * @param {number} wait - Wait time in ms
     * @returns {Function} - Debounced function
     */
    function debounce(func, wait = 300) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // ============================================
    // DATE UTILITIES
    // ============================================

    /**
     * Get date range for common periods
     * @param {string} period - Period type ('today', 'week', 'month', 'quarter', 'year')
     * @returns {Object} - {start_date, end_date}
     */
    function getDateRange(period) {
        const today = new Date();
        const year = today.getFullYear();
        const month = today.getMonth();
        
        let start, end;

        switch (period) {
            case 'today':
                start = end = formatDateForInput(today);
                break;
            
            case 'week':
                start = new Date(today);
                start.setDate(today.getDate() - 7);
                start = formatDateForInput(start);
                end = formatDateForInput(today);
                break;
            
            case 'month':
                start = new Date(year, month, 1);
                end = new Date(year, month + 1, 0);
                start = formatDateForInput(start);
                end = formatDateForInput(end);
                break;
            
            case 'quarter':
                const quarter = Math.floor(month / 3);
                start = new Date(year, quarter * 3, 1);
                end = new Date(year, quarter * 3 + 3, 0);
                start = formatDateForInput(start);
                end = formatDateForInput(end);
                break;
            
            case 'year':
                start = new Date(year, 0, 1);
                end = new Date(year, 11, 31);
                start = formatDateForInput(start);
                end = formatDateForInput(end);
                break;
            
            default:
                start = end = '';
        }

        return { start_date: start, end_date: end };
    }

    /**
     * Format date for input fields (YYYY-MM-DD)
     * @param {Date} date - Date object
     * @returns {string} - Formatted date
     */
    function formatDateForInput(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    /**
     * Set date inputs to previous month (1st to last day)
     * @param {string} fromId - ID of the from-date input (default: 'fromDate')
     * @param {string} toId - ID of the to-date input (default: 'toDate')
     */
    function setDefaultPreviousMonth(fromId = 'fromDate', toId = 'toDate') {
        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        const lastDay = new Date(today.getFullYear(), today.getMonth(), 0);
        const fromEl = document.getElementById(fromId);
        const toEl = document.getElementById(toId);
        if (fromEl && !fromEl.value) fromEl.value = formatDateForInput(firstDay);
        if (toEl && !toEl.value) toEl.value = formatDateForInput(lastDay);
    }

    // ============================================
    // COMPANY DROPDOWN HELPER
    // ============================================

    /**
     * Populate a company filter <select> from the API.
     * Call once on page init: TallySyncCommon.loadCompanies('companyFilter')
     */
    async function loadCompanies(selectId) {
        const sel = document.getElementById(selectId);
        if (!sel) return;
        try {
            const data = await apiCall('companies');
            if (data.companies) {
                data.companies.forEach(function(c) {
                    var opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = c.name;
                    sel.appendChild(opt);
                });
            }
        } catch (e) {
            // Silently fail — dropdown stays with "All Companies" only
        }
    }

    // ============================================
    // EXPORT PUBLIC API
    // ============================================

    return {
        // API
        apiCall,
        getFilters,

        // UI
        setLoading,
        showError,
        showSuccess,

        // Charts
        createChart,
        destroyChart,
        getDefaultChartOptions,
        CHART_COLORS,

        // Formatting
        formatCurrency,
        formatNumber,
        formatDate,
        formatMonth,
        formatPercentage,

        // Data
        getNestedValue,
        deepMerge,
        debounce,

        // Date
        getDateRange,
        formatDateForInput,
        setDefaultPreviousMonth,

        // Dropdowns
        loadCompanies
    };

})();

// Make available globally
window.TallySyncCommon = TallySyncCommon;