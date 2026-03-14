// Gmail Compose JavaScript
// Handles compose modal, draft auto-save, and sending emails

// Global compose state
let draftAutoSaveInterval = null;
let currentDraftId = null;
let isDraftSaving = false;
let lastDraftContent = '';

// getCsrfToken() is loaded globally from csrf-utils.js

// Open compose modal
function openComposeModal(replyTo = null, subject = null, body = null) {
    const modal = document.getElementById('compose-modal');
    modal.classList.remove('hidden');

    // Pre-fill if reply context provided
    if (replyTo) {
        document.getElementById('compose-to').value = replyTo;
    }
    if (subject) {
        document.getElementById('compose-subject').value = subject;
    }
    if (body) {
        document.getElementById('compose-body').value = body;
    }

    // Load signature for currently selected account
    const fromSelect = document.getElementById('compose-from');
    if (fromSelect && fromSelect.value) {
        loadSignatureForAccount(fromSelect.value);
    }

    // Start auto-save
    startDraftAutoSave();

    // Focus on To field if empty, otherwise body
    if (!replyTo) {
        document.getElementById('compose-to').focus();
    } else {
        document.getElementById('compose-body').focus();
    }
}

// Close compose modal
function closeComposeModal() {
    // Ask to save draft if there's content
    const hasContent = checkHasContent();

    if (hasContent) {
        if (confirm('Do you want to save this as a draft?')) {
            saveDraft(true); // Save and close
        }
    }

    const modal = document.getElementById('compose-modal');
    modal.classList.add('hidden');

    // Stop auto-save
    stopDraftAutoSave();

    // Clear form
    clearComposeForm();
}

// Check if compose form has content
function checkHasContent() {
    const to = document.getElementById('compose-to').value.trim();
    const subject = document.getElementById('compose-subject').value.trim();
    const body = document.getElementById('compose-body').value.trim();

    return to || subject || body;
}

// Clear compose form
function clearComposeForm() {
    document.getElementById('compose-form').reset();
    document.getElementById('compose-to').value = '';
    document.getElementById('compose-cc').value = '';
    document.getElementById('compose-bcc').value = '';
    document.getElementById('compose-subject').value = '';
    document.getElementById('compose-body').value = '';
    document.getElementById('attachment-list').innerHTML = '';

    // Hide Cc/Bcc fields
    document.getElementById('cc-field').classList.add('hidden');
    document.getElementById('bcc-field').classList.add('hidden');
    document.getElementById('toggle-cc-bcc').textContent = '+ Add Cc/Bcc';

    // Clear signature
    const sigWrap = document.getElementById('compose-signature-wrap');
    const sigEl = document.getElementById('compose-signature');
    if (sigWrap) sigWrap.classList.add('hidden');
    if (sigEl) sigEl.innerHTML = '';

    currentDraftId = null;
    lastDraftContent = '';
}

// ─── Signature Loading ──────────────────────────────────────────────────────

async function loadSignatureForAccount(tokenId) {
    if (!tokenId) return;
    const sigUrl = window.GMAIL_CONFIG && window.GMAIL_CONFIG.signatureUrl;
    if (!sigUrl) return;

    try {
        const resp = await fetch(`${sigUrl}?token_id=${tokenId}`);
        const data = await resp.json();

        const sigWrap = document.getElementById('compose-signature-wrap');
        const sigEl = document.getElementById('compose-signature');

        if (data.signature && sigWrap && sigEl) {
            sigEl.innerHTML = data.signature;
            sigWrap.classList.remove('hidden');
        } else if (sigWrap) {
            sigWrap.classList.add('hidden');
            if (sigEl) sigEl.innerHTML = '';
        }
    } catch (e) {
        // Silently ignore signature load errors — non-critical
        const sigWrap = document.getElementById('compose-signature-wrap');
        if (sigWrap) sigWrap.classList.add('hidden');
    }
}

// Start draft auto-save
function startDraftAutoSave() {
    // Clear any existing interval
    stopDraftAutoSave();

    // Auto-save every 30 seconds (content-change detection in autoSaveDraft prevents unnecessary saves)
    draftAutoSaveInterval = setInterval(() => {
        autoSaveDraft();
    }, 30000);
}

// Stop draft auto-save
function stopDraftAutoSave() {
    if (draftAutoSaveInterval) {
        clearInterval(draftAutoSaveInterval);
        draftAutoSaveInterval = null;
    }
}

// Auto-save draft (called by interval)
async function autoSaveDraft() {
    // Only save if there's content and it's changed
    if (!checkHasContent()) {
        return;
    }

    const currentContent = getComposeFormContent();
    if (currentContent === lastDraftContent) {
        return; // No changes
    }

    await saveDraft(false);
}

// Get compose form content as JSON string (for change detection)
function getComposeFormContent() {
    const formData = {
        to: document.getElementById('compose-to').value.trim(),
        cc: document.getElementById('compose-cc').value.trim(),
        bcc: document.getElementById('compose-bcc').value.trim(),
        subject: document.getElementById('compose-subject').value.trim(),
        body: document.getElementById('compose-body').value.trim()
    };
    return JSON.stringify(formData);
}

// Save draft
async function saveDraft(closeAfterSave = false) {
    if (isDraftSaving) {
        return; // Already saving
    }

    const fromAccount = document.getElementById('compose-from').value;
    const to = document.getElementById('compose-to').value.trim();
    const cc = document.getElementById('compose-cc').value.trim();
    const bcc = document.getElementById('compose-bcc').value.trim();
    const subject = document.getElementById('compose-subject').value.trim();
    const body = document.getElementById('compose-body').value.trim();

    // Must have at least one recipient or subject or body
    if (!to && !subject && !body) {
        return;
    }

    isDraftSaving = true;
    updateDraftStatus('Saving...');

    try {
        // Use field names matching the save_draft action
        const requestData = {
            account_id: fromAccount,
            to_emails: to,
            cc_emails: cc,
            bcc_emails: bcc,
            subject: subject,
            body_html: body.replace(/\n/g, '<br>')
        };

        // If updating existing draft
        if (currentDraftId) {
            requestData.draft_id = currentDraftId;
        }

        const response = await fetch('/gmail/api/save-draft/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        if (data.success) {
            currentDraftId = data.draft_id;
            lastDraftContent = getComposeFormContent();
            updateDraftStatus('Saved', true);

            if (closeAfterSave) {
                setTimeout(() => {
                    closeComposeModal();
                }, 500);
            }
        } else {
            updateDraftStatus('Save failed', false);
            console.error('Failed to save draft:', data.error);
        }
    } catch (error) {
        console.error('Error saving draft:', error);
        updateDraftStatus('Save failed', false);
    } finally {
        isDraftSaving = false;
    }
}

// Update draft status indicator
function updateDraftStatus(message, success = null) {
    const statusEl = document.getElementById('draft-status');
    statusEl.textContent = message;

    if (success === true) {
        statusEl.className = 'text-xs text-green-600';
        // Clear success message after 2 seconds
        setTimeout(() => {
            statusEl.textContent = '';
        }, 2000);
    } else if (success === false) {
        statusEl.className = 'text-xs text-red-600';
    } else {
        statusEl.className = 'text-xs text-gray-500';
    }
}

// Send email
async function sendEmail() {
    const fromAccount = document.getElementById('compose-from').value;
    const to = document.getElementById('compose-to').value.trim();
    const cc = document.getElementById('compose-cc').value.trim();
    const bcc = document.getElementById('compose-bcc').value.trim();
    const subject = document.getElementById('compose-subject').value.trim();
    const body = document.getElementById('compose-body').value.trim();

    // Append signature if present
    const sigEl = document.getElementById('compose-signature');
    const sigWrap = document.getElementById('compose-signature-wrap');
    const signatureHtml = (sigEl && sigWrap && !sigWrap.classList.contains('hidden'))
        ? `<br><br>--<br>${sigEl.innerHTML}`
        : '';

    // Validation
    if (!fromAccount) {
        alert('Please select a sender account');
        return;
    }

    if (!to) {
        alert('Please enter at least one recipient');
        return;
    }

    if (!subject) {
        if (!confirm('Send without a subject?')) {
            return;
        }
    }

    if (!body) {
        if (!confirm('Send empty message?')) {
            return;
        }
    }

    // Stop auto-save while sending
    stopDraftAutoSave();

    // Show sending status
    updateDraftStatus('Sending...');

    try {
        // Build JSON payload matching the send_email action's expected fields
        const payload = {
            account_id: fromAccount,
            to_emails: to,
            cc_emails: cc,
            bcc_emails: bcc,
            subject: subject,
            body_html: body.replace(/\n/g, '<br>') + signatureHtml
        };

        const response = await fetch('/gmail/api/send/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            updateDraftStatus('Sent!', true);

            // Close modal after short delay
            setTimeout(() => {
                closeComposeModal();

                // Show success message
                showNotification('Email sent successfully', 'success');

                // If on inbox page, reload threads
                if (typeof loadThreads === 'function') {
                    loadThreads();
                }
            }, 1000);
        } else {
            updateDraftStatus('Send failed', false);
            alert('Failed to send email: ' + (data.error || 'Unknown error'));
            // Restart auto-save
            startDraftAutoSave();
        }
    } catch (error) {
        console.error('Error sending email:', error);
        updateDraftStatus('Send failed', false);
        alert('Failed to send email. Please try again.');
        // Restart auto-save
        startDraftAutoSave();
    }
}

// Show notification (simple toast)
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 ${
        type === 'success' ? 'bg-green-500 text-white' :
        type === 'error' ? 'bg-red-500 text-white' :
        'bg-blue-500 text-white'
    }`;
    notification.textContent = message;

    document.body.appendChild(notification);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Handle attachment file selection
document.addEventListener('DOMContentLoaded', function() {
    const attachmentsInput = document.getElementById('compose-attachments');
    if (attachmentsInput) {
        attachmentsInput.addEventListener('change', function() {
            displayAttachmentList();
        });
    }

    // Reload signature when "From" account changes
    const fromSelect = document.getElementById('compose-from');
    if (fromSelect) {
        fromSelect.addEventListener('change', function() {
            const modal = document.getElementById('compose-modal');
            if (modal && !modal.classList.contains('hidden')) {
                loadSignatureForAccount(this.value);
            }
        });
    }
});

// Display selected attachments
function displayAttachmentList() {
    const attachmentsInput = document.getElementById('compose-attachments');
    const attachmentList = document.getElementById('attachment-list');

    if (!attachmentsInput.files.length) {
        attachmentList.innerHTML = '';
        return;
    }

    let html = '<div class="space-y-1">';
    for (let i = 0; i < attachmentsInput.files.length; i++) {
        const file = attachmentsInput.files[i];
        const sizeKB = (file.size / 1024).toFixed(1);
        html += `
            <div class="flex items-center justify-between p-2 bg-gray-50 rounded border border-gray-200">
                <div class="flex items-center space-x-2">
                    <svg class="h-4 w-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"></path>
                    </svg>
                    <span class="text-sm text-gray-700">${file.name}</span>
                    <span class="text-xs text-gray-500">(${sizeKB} KB)</span>
                </div>
                <button
                    type="button"
                    onclick="removeAttachment(${i})"
                    class="text-red-600 hover:text-red-700"
                >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;
    }
    html += '</div>';
    attachmentList.innerHTML = html;
}

// Remove attachment (note: can't actually remove from FileList, so we'd need to rebuild it)
function removeAttachment(index) {
    const attachmentsInput = document.getElementById('compose-attachments');
    const dt = new DataTransfer();

    for (let i = 0; i < attachmentsInput.files.length; i++) {
        if (i !== index) {
            dt.items.add(attachmentsInput.files[i]);
        }
    }

    attachmentsInput.files = dt.files;
    displayAttachmentList();
}

// Handle Escape key to close modal
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const modal = document.getElementById('compose-modal');
        if (modal && !modal.classList.contains('hidden')) {
            closeComposeModal();
        }
    }
});

// Prevent accidental navigation away
window.addEventListener('beforeunload', function(e) {
    const modal = document.getElementById('compose-modal');
    if (modal && !modal.classList.contains('hidden') && checkHasContent()) {
        e.preventDefault();
        e.returnValue = '';
        return '';
    }
});

// Export functions for use in other scripts
if (typeof window !== 'undefined') {
    window.openComposeModal = openComposeModal;
    window.closeComposeModal = closeComposeModal;
    window.saveDraft = saveDraft;
    window.sendEmail = sendEmail;
    window.loadSignatureForAccount = loadSignatureForAccount;
}
