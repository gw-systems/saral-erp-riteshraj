// Gmail Inbox JavaScript
// Handles thread loading, message display, and email actions

// Global state
let currentThreadId = null;
let currentThread = null;  // Full thread data from API
let currentView = 'inbox';
let currentAccount = '';
let currentPage = 1;
let totalPages = 1;
let threads = [];

// getCsrfToken() is loaded globally from csrf-utils.js

// Generate random avatar color based on email
function getAvatarColor(email) {
    const colors = [
        '#EF4444', '#F59E0B', '#10B981', '#3B82F6',
        '#6366F1', '#8B5CF6', '#EC4899', '#14B8A6'
    ];
    let hash = 0;
    for (let i = 0; i < email.length; i++) {
        hash = email.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
}

// Get initials from name or email
function getInitials(name) {
    if (!name) return '?';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
}

// Format date for display
function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    } else if (diffDays === 1) {
        return 'Yesterday';
    } else if (diffDays < 7) {
        return date.toLocaleDateString('en-US', { weekday: 'short' });
    } else {
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
}

// Initialize inbox
function initInbox() {
    loadAccounts();
    loadThreads();
    setupEventListeners();
}

// Load available Gmail accounts (only for compose-from dropdown — account filter is server-rendered)
async function loadAccounts() {
    try {
        const response = await fetch('/gmail/api/accounts/');
        const data = await response.json();
        const composeFrom = document.getElementById('compose-from');
        if (!composeFrom) return;

        (data.accounts || []).forEach(account => {
            const option = document.createElement('option');
            option.value = account.id;
            option.textContent = account.email;
            composeFrom.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading accounts:', error);
    }
}

// Load threads with optional search query
function loadThreadsWithSearch(query) {
    loadThreads(query);
}

// Load threads
async function loadThreads(searchQuery) {
    const container = document.getElementById('thread-list-items');
    container.innerHTML = `
        <div class="flex items-center justify-center p-8">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
    `;

    try {
        const params = new URLSearchParams({
            view: currentView,
            page: currentPage,
            account: currentAccount
        });

        if (searchQuery) {
            params.set('search', searchQuery);
        }

        const response = await fetch(`/gmail/api/threads/?${params}`);
        const data = await response.json();

        if (data.threads !== undefined) {
            threads = data.threads;
            totalPages = data.total_pages || 1;
            renderThreads(threads);
            updatePagination();
        } else {
            container.innerHTML = `
                <div class="p-8 text-center text-gray-500">
                    <p>Error loading threads</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading threads:', error);
        container.innerHTML = `
            <div class="p-8 text-center text-gray-500">
                <p>Failed to load emails</p>
            </div>
        `;
    }
}

// Render thread list
function renderThreads(threads) {
    const container = document.getElementById('thread-list-items');

    if (threads.length === 0) {
        container.innerHTML = `
            <div class="p-8 text-center text-gray-500">
                <svg class="mx-auto h-12 w-12 text-gray-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path>
                </svg>
                <p>No emails found</p>
            </div>
        `;
        return;
    }

    container.innerHTML = threads.map(thread => {
        const threadId = thread.thread_id;
        const senderName = thread.last_sender_name || thread.sender_email || 'Unknown';
        const initials = getInitials(senderName);
        const color = getAvatarColor(thread.sender_email || senderName);
        const isUnread = thread.has_unread;
        const isStarred = thread.is_starred;
        const msgCount = thread.message_count || 1;
        const countBadge = msgCount > 1
            ? `<span class="text-xs text-gray-500 font-medium flex-shrink-0">${msgCount}</span>`
            : '';

        return `
            <div class="thread-item ${isUnread ? 'unread' : ''} ${currentThreadId === threadId ? 'active' : ''} px-4 py-3.5 border-b border-gray-100"
                 onclick="selectThread('${threadId}')"
                 data-thread-id="${threadId}">
                <div class="flex items-start gap-3">
                    <!-- Avatar -->
                    <div class="avatar flex-shrink-0 mt-0.5" style="background-color:${color}; width:38px; height:38px; font-size:0.8rem;">${initials}</div>
                    <!-- Content -->
                    <div class="flex-1 min-w-0">
                        <!-- Row 1: Sender + Date + Unread dot -->
                        <div class="flex items-center justify-between gap-2 mb-0.5">
                            <span class="thread-sender text-sm truncate ${isUnread ? 'font-bold text-gray-900' : 'font-semibold text-gray-700'}">${senderName}</span>
                            <div class="flex items-center gap-1.5 flex-shrink-0">
                                ${isUnread ? '<div class="unread-dot"></div>' : ''}
                                <span class="text-xs text-gray-500 whitespace-nowrap">${formatDate(thread.last_message_date)}</span>
                            </div>
                        </div>
                        <!-- Row 2: Subject + Star + Count -->
                        <div class="flex items-center justify-between gap-2 mb-0.5">
                            <span class="thread-subject text-xs truncate ${isUnread ? 'font-semibold text-gray-800' : 'text-gray-600'}">${thread.subject || '(No subject)'}</span>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                ${countBadge}
                                <svg class="star-icon w-3.5 h-3.5 flex-shrink-0 ${isStarred ? 'starred' : 'text-gray-300'}"
                                     fill="${isStarred ? 'currentColor' : 'none'}"
                                     stroke="currentColor" viewBox="0 0 24 24"
                                     onclick="event.stopPropagation(); toggleStar('${threadId}')">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>
                                </svg>
                            </div>
                        </div>
                        <!-- Row 3: Snippet -->
                        <p class="text-xs text-gray-500 truncate leading-4">${thread.snippet || ''}</p>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Update pagination controls
function updatePagination() {
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');
    const pageInfo = document.getElementById('page-info');

    prevBtn.disabled = currentPage <= 1;
    nextBtn.disabled = currentPage >= totalPages;
    pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
}

// Select and load a thread
async function selectThread(threadId) {
    currentThreadId = threadId;

    // Update active state in thread list
    document.querySelectorAll('.thread-item').forEach(item => {
        item.classList.remove('active');
    });
    const selectedItem = document.querySelector(`[data-thread-id="${threadId}"]`);
    if (selectedItem) {
        selectedItem.classList.add('active');
        selectedItem.classList.remove('unread');
    }

    // Show conversation view
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('conversation-view').classList.remove('hidden');

    // Load thread messages
    await loadThread(threadId);
}

// Load thread messages
async function loadThread(threadId) {
    const messagesContainer = document.getElementById('messages-container');
    messagesContainer.innerHTML = `
        <div class="flex items-center justify-center p-8">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
    `;

    try {
        const response = await fetch(`/gmail/api/thread/${threadId}/`);
        const data = await response.json();

        if (data.success) {
            currentThread = data.thread;  // Save for quick reply use
            renderThread(data.thread);

            // Mark unread messages as read - pass actual message_ids
            if (data.thread.has_unread) {
                const unreadMessageIds = data.thread.messages
                    .filter(m => !m.is_read)
                    .map(m => m.message_id);
                if (unreadMessageIds.length > 0) {
                    await markAsRead(unreadMessageIds);
                }
            }
        } else {
            messagesContainer.innerHTML = `
                <div class="p-8 text-center text-gray-500">
                    <p>Error loading conversation</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading thread:', error);
        messagesContainer.innerHTML = `
            <div class="p-8 text-center text-gray-500">
                <p>Failed to load conversation</p>
            </div>
        `;
    }
}

// Render thread messages — email-trail style (not chat bubbles)
function renderThread(thread) {
    const subjectEl = document.getElementById('thread-subject');
    const participantsEl = document.getElementById('thread-participants');
    const messagesContainer = document.getElementById('messages-container');
    const starButton = document.getElementById('star-button');

    subjectEl.textContent = thread.subject || '(No subject)';

    const participants = thread.participants || [];
    participantsEl.textContent = participants.map(p => p.name || p.email).join(', ');

    if (thread.is_starred) {
        starButton.classList.add('text-yellow-500');
        starButton.querySelector('svg').setAttribute('fill', 'currentColor');
    } else {
        starButton.classList.remove('text-yellow-500');
        starButton.querySelector('svg').setAttribute('fill', 'none');
    }

    const currentAccountEmail = thread.account_email || '';

    function formatSize(bytes) {
        if (!bytes) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function buildMessageCard(message, idx) {
        const fromContact = message.from || {};
        const senderName = fromContact.name || fromContact.email || 'Unknown';
        const senderEmail = fromContact.email || '';
        const initials = fromContact.initial || getInitials(senderName);
        const color = getAvatarColor(senderEmail || senderName);
        const isFromMe = currentAccountEmail && senderEmail.toLowerCase() === currentAccountEmail.toLowerCase();

        // To / Cc lines
        const toList = (message.to || []).map(c => c.name || c.email).join(', ');
        const ccList = (message.cc || []).map(c => c.name || c.email).join(', ');
        const recipientHtml = toList
            ? `<span class="text-xs text-gray-500"><span class="font-medium text-gray-500">to</span> ${toList}${ccList ? ` &nbsp;·&nbsp; <span class="font-medium text-gray-500">cc</span> ${ccList}` : ''}</span>`
            : '';

        // Attachments
        let attachmentsHtml = '';
        if (message.attachments && message.attachments.length > 0) {
            attachmentsHtml = `
                <div class="mt-3 pt-3 border-t border-gray-100 flex flex-wrap gap-2">
                    ${message.attachments.map(att => `
                        <a href="/gmail/api/attachment/${att.id}/download/" class="att-chip" title="Download ${att.filename}">
                            <svg class="w-3.5 h-3.5 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/>
                            </svg>
                            <span class="truncate max-w-[180px]">${att.filename}</span>
                            <span class="text-gray-500 flex-shrink-0">${formatSize(att.size)}</span>
                        </a>
                    `).join('')}
                </div>`;
        }

        const dateDisplay = message.date_display || formatDate(message.date);

        return `
        <div class="email-card ${isFromMe ? 'from-me' : ''}">
            <!-- Message Header -->
            <div class="email-card-header">
                <div class="flex items-center gap-3 min-w-0">
                    <div class="avatar flex-shrink-0" style="background-color:${color}; width:36px; height:36px; font-size:0.75rem;">${initials}</div>
                    <div class="min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-sm font-semibold ${isFromMe ? 'text-blue-700' : 'text-gray-900'}">${senderName}</span>
                            <span class="text-xs text-gray-500">&lt;${senderEmail}&gt;</span>
                        </div>
                        ${recipientHtml ? `<div class="mt-0.5">${recipientHtml}</div>` : ''}
                    </div>
                </div>
                <div class="flex items-center gap-2 flex-shrink-0 ml-3">
                    <span class="text-xs text-gray-500 whitespace-nowrap">${dateDisplay}</span>
                </div>
            </div>
            <!-- Message Body -->
            <div class="email-card-body message-body">
                ${message.body_html
                    ? message.body_html
                    : (message.body_text
                        ? `<pre class="whitespace-pre-wrap font-sans text-sm text-gray-700">${message.body_text}</pre>`
                        : '<em class="text-gray-500 text-xs">(No content)</em>')}
            </div>
            ${attachmentsHtml}
        </div>`;
    }

    const messages = thread.messages;
    const total = messages.length;
    const COLLAPSE_THRESHOLD = 4; // show collapse button when > this many messages

    let html = '';
    if (total <= COLLAPSE_THRESHOLD) {
        html = messages.map((m, i) => buildMessageCard(m, i)).join('');
    } else {
        // Show first + last 2, collapse middle
        const first = buildMessageCard(messages[0], 0);
        const hiddenCount = total - 3;
        const collapseBtn = `
            <div class="email-collapse-btn" onclick="expandCollapsedMessages(this)">
                <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                </svg>
                <span>${hiddenCount} earlier message${hiddenCount > 1 ? 's' : ''} — click to expand</span>
            </div>
            <div class="email-collapsed-messages hidden">
                ${messages.slice(1, total - 2).map((m, i) => buildMessageCard(m, i + 1)).join('')}
            </div>`;
        const last2 = messages.slice(total - 2).map((m, i) => buildMessageCard(m, total - 2 + i)).join('');
        html = first + collapseBtn + last2;
    }

    messagesContainer.innerHTML = html;
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function expandCollapsedMessages(btn) {
    const collapsed = btn.nextElementSibling;
    collapsed.classList.remove('hidden');
    btn.classList.add('hidden');
}

// Mark messages as read
async function markAsRead(messageIds) {
    try {
        const response = await fetch('/gmail/api/mark-read/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ message_ids: messageIds })
        });

        const data = await response.json();
        return data.success;
    } catch (error) {
        console.error('Error marking as read:', error);
        return false;
    }
}

// Archive thread
async function archiveThread(threadId) {
    try {
        const response = await fetch('/gmail/api/archive/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ thread_id: threadId })
        });

        const data = await response.json();

        if (data.success) {
            // Remove from list and reload
            currentThreadId = null;
            document.getElementById('conversation-view').classList.add('hidden');
            document.getElementById('empty-state').classList.remove('hidden');
            await loadThreads();
        }

        return data.success;
    } catch (error) {
        console.error('Error archiving thread:', error);
        return false;
    }
}

// Toggle star on thread
async function toggleStar(threadId) {
    try {
        const response = await fetch('/gmail/api/toggle-star/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ thread_id: threadId })
        });

        const data = await response.json();

        if (data.success) {
            const isStarred = data.is_starred;

            // Update UI in thread list
            const starIcon = document.querySelector(`[data-thread-id="${threadId}"] .star-icon`);
            if (starIcon) {
                if (isStarred) {
                    starIcon.classList.add('starred');
                    starIcon.setAttribute('fill', 'currentColor');
                } else {
                    starIcon.classList.remove('starred');
                    starIcon.setAttribute('fill', 'none');
                }
            }

            // If currently viewing this thread, update header star
            if (currentThreadId === threadId) {
                const headerStar = document.getElementById('star-button');
                if (isStarred) {
                    headerStar.classList.add('text-yellow-500');
                    headerStar.querySelector('svg').setAttribute('fill', 'currentColor');
                } else {
                    headerStar.classList.remove('text-yellow-500');
                    headerStar.querySelector('svg').setAttribute('fill', 'none');
                }
            }
        }

        return data.success;
    } catch (error) {
        console.error('Error toggling star:', error);
        return false;
    }
}

// Delete thread
async function deleteThread(threadId) {
    if (!confirm('Are you sure you want to delete this conversation?')) {
        return false;
    }

    try {
        const response = await fetch('/gmail/api/delete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ thread_id: threadId })
        });

        const data = await response.json();

        if (data.success) {
            // Remove from list and reload
            currentThreadId = null;
            document.getElementById('conversation-view').classList.add('hidden');
            document.getElementById('empty-state').classList.remove('hidden');
            await loadThreads();
        }

        return data.success;
    } catch (error) {
        console.error('Error deleting thread:', error);
        return false;
    }
}

// Send quick reply
async function sendQuickReply() {
    const input = document.getElementById('quick-reply-input');
    const body = input.value.trim();

    if (!body) {
        alert('Please enter a message');
        return;
    }

    if (!currentThreadId || !currentThread) {
        alert('No conversation selected');
        return;
    }

    // Get the account selector or derive from current thread
    const composeFrom = document.getElementById('compose-from');
    let accountId = composeFrom ? composeFrom.value : null;

    // If no account selected, try to find from thread's account
    if (!accountId) {
        // Fallback: get accounts list and find matching one
        try {
            const resp = await fetch('/gmail/api/accounts/');
            const accData = await resp.json();
            const matchingAcc = accData.accounts.find(a => a.email === currentThread.account_email);
            if (matchingAcc) accountId = matchingAcc.id;
            else if (accData.accounts.length > 0) accountId = accData.accounts[0].id;
        } catch (e) {
            console.error('Could not get account:', e);
        }
    }

    if (!accountId) {
        alert('No Gmail account selected. Please select a sender account.');
        return;
    }

    // Build reply-to email from thread participants (exclude our own account)
    const replyTo = currentThread.participants
        .filter(p => p.email !== currentThread.account_email)
        .map(p => p.email)
        .join(', ');

    const replySubject = currentThread.subject
        ? (currentThread.subject.startsWith('Re:') ? currentThread.subject : 'Re: ' + currentThread.subject)
        : '';

    try {
        const response = await fetch('/gmail/api/send/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                account_id: accountId,
                to_emails: replyTo || currentThread.participants.map(p => p.email).join(', '),
                subject: replySubject,
                body_html: body.replace(/\n/g, '<br>'),
                thread_id: currentThreadId
            })
        });

        const data = await response.json();

        if (data.success) {
            input.value = '';
            // Reload thread to show new message
            await loadThread(currentThreadId);
        } else {
            alert('Failed to send message: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error sending reply:', error);
        alert('Failed to send message');
    }
}

// Action wrappers for current thread
function archiveCurrentThread() {
    if (currentThreadId) {
        archiveThread(currentThreadId);
    }
}

function toggleStarCurrentThread() {
    if (currentThreadId) {
        toggleStar(currentThreadId);
    }
}

async function markCurrentThreadUnread() {
    if (!currentThreadId) return;

    try {
        // Get the last message in the current thread and mark it unread
        const response = await fetch(`/gmail/api/thread/${currentThreadId}/`);
        const data = await response.json();

        if (data.success && data.thread.messages.length > 0) {
            // Mark the last message as unread
            const lastMessage = data.thread.messages[data.thread.messages.length - 1];
            await fetch('/gmail/api/mark-unread/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ message_ids: [lastMessage.message_id] })
            });

            // Update thread item in list to show as unread
            const threadItem = document.querySelector(`[data-thread-id="${currentThreadId}"]`);
            if (threadItem) {
                threadItem.classList.add('unread');
            }
        }
    } catch (error) {
        console.error('Error marking thread as unread:', error);
    }
}

function deleteCurrentThread() {
    if (currentThreadId) {
        deleteThread(currentThreadId);
    }
}

// Open full composer with reply context
function openFullComposer() {
    if (currentThreadId) {
        // Pre-fill compose modal with reply context
        const thread = threads.find(t => t.thread_id === currentThreadId);
        if (thread) {
            document.getElementById('compose-subject').value = 'Re: ' + (thread.subject || '');
            document.getElementById('compose-to').value = thread.sender_email || '';
        }
    }
    openComposeModal();
}

// Setup event listeners
function setupEventListeners() {
    // View tabs
    document.querySelectorAll('.view-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            currentView = this.dataset.view;
            currentPage = 1;
            loadThreads();
        });
    });

    // Account filter
    document.getElementById('account-filter').addEventListener('change', function() {
        currentAccount = this.value;
        currentPage = 1;
        loadThreads();
    });

    // Search
    let searchTimeout;
    let currentSearch = '';
    document.getElementById('search-input').addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim();
        searchTimeout = setTimeout(() => {
            currentSearch = query;
            currentPage = 1;
            loadThreadsWithSearch(query);
        }, 400);
    });

    // Pagination
    document.getElementById('prev-page').addEventListener('click', function() {
        if (currentPage > 1) {
            currentPage--;
            loadThreads();
        }
    });

    document.getElementById('next-page').addEventListener('click', function() {
        if (currentPage < totalPages) {
            currentPage++;
            loadThreads();
        }
    });

    // Quick reply - handle Enter key
    document.getElementById('quick-reply-input').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuickReply();
        }
    });
}
