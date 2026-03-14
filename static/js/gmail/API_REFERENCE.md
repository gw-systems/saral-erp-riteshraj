# Gmail Inbox API Reference

This document outlines the API endpoints expected by the Gmail inbox frontend.

## Required API Endpoints

### 1. GET /gmail/api/accounts/
**Purpose:** Load available Gmail accounts for filtering and composing

**Response:**
```json
{
  "success": true,
  "accounts": [
    {
      "id": 1,
      "email": "user@example.com"
    }
  ]
}
```

---

### 2. GET /gmail/api/threads/
**Purpose:** Load thread list with pagination and filtering

**Query Parameters:**
- `view`: "all" | "unread" | "starred" | "archived"
- `page`: Page number (default: 1)
- `account`: Account ID filter (optional)

**Response:**
```json
{
  "success": true,
  "threads": [
    {
      "id": "thread_123",
      "sender_name": "John Doe",
      "sender_email": "john@example.com",
      "subject": "Meeting tomorrow",
      "snippet": "Just wanted to confirm...",
      "date": "2026-02-16T10:30:00Z",
      "unread": true,
      "starred": false
    }
  ],
  "total_pages": 5,
  "current_page": 1
}
```

---

### 3. GET /gmail/api/thread/{threadId}/
**Purpose:** Load full thread with all messages

**Response:**
```json
{
  "success": true,
  "thread": {
    "id": "thread_123",
    "subject": "Meeting tomorrow",
    "participants": ["john@example.com", "jane@example.com"],
    "unread": false,
    "starred": false,
    "messages": [
      {
        "id": "msg_1",
        "sender_name": "John Doe",
        "sender_email": "john@example.com",
        "date": "2026-02-16T10:30:00Z",
        "body_html": "<p>Message content</p>",
        "body_text": "Message content",
        "from_me": false,
        "attachments": [
          {
            "filename": "document.pdf",
            "size": "1.2 MB",
            "url": "/media/attachments/doc.pdf"
          }
        ]
      }
    ]
  }
}
```

---

### 4. POST /gmail/api/mark-read/
**Purpose:** Mark messages as read

**Request Body:**
```json
{
  "message_ids": ["msg_1", "msg_2"]
}
```

**Response:**
```json
{
  "success": true
}
```

---

### 5. POST /gmail/api/archive/
**Purpose:** Archive a thread

**Request Body:**
```json
{
  "thread_id": "thread_123"
}
```

**Response:**
```json
{
  "success": true
}
```

---

### 6. POST /gmail/api/toggle-star/
**Purpose:** Toggle star status on a thread

**Request Body:**
```json
{
  "thread_id": "thread_123"
}
```

**Response:**
```json
{
  "success": true,
  "starred": true
}
```

---

### 7. POST /gmail/api/delete/
**Purpose:** Delete a thread

**Request Body:**
```json
{
  "thread_id": "thread_123"
}
```

**Response:**
```json
{
  "success": true
}
```

---

### 8. POST /gmail/api/send/
**Purpose:** Send an email or quick reply

**Request Body (Quick Reply):**
```json
{
  "thread_id": "thread_123",
  "body": "Reply message"
}
```

**Request Body (New Email - FormData):**
- `from_account`: Account ID
- `to`: Recipient emails (comma-separated)
- `cc`: CC emails (optional)
- `bcc`: BCC emails (optional)
- `subject`: Email subject
- `body`: Email body (HTML or plain text)
- `draft_id`: Draft ID if continuing from draft (optional)
- `attachments`: File uploads (multiple)

**Response:**
```json
{
  "success": true,
  "message_id": "msg_456"
}
```

---

### 9. POST /gmail/api/save-draft/
**Purpose:** Save or update a draft

**Request Body:**
```json
{
  "draft_id": "draft_789",  // optional, omit for new draft
  "from_account": 1,
  "to": "recipient@example.com",
  "cc": "",
  "bcc": "",
  "subject": "Draft subject",
  "body": "Draft content"
}
```

**Response:**
```json
{
  "success": true,
  "draft_id": "draft_789"
}
```

---

## Error Responses

All endpoints should return consistent error responses:

```json
{
  "success": false,
  "error": "Error message description"
}
```

---

## CSRF Protection

All POST requests include the CSRF token in the `X-CSRFToken` header, extracted from the `csrftoken` cookie.

---

## Notes

1. **Date Format:** All dates should be in ISO 8601 format (e.g., "2026-02-16T10:30:00Z")
2. **Email Addresses:** Can be comma-separated strings for multiple recipients
3. **File Uploads:** Use FormData for endpoints that accept attachments
4. **Pagination:** Default page size should be 20-50 threads
5. **Thread IDs:** Should be unique identifiers (strings or numbers)
6. **Auto-save:** Drafts auto-save every 3 seconds when content changes
