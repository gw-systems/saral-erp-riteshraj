/**
 * Shared CSRF token utility
 * Extracts the CSRF token from browser cookies for AJAX requests
 */
function getCsrfToken() {
    return document.cookie.split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1] || '';
}
