# Enterprise Notification System - User Guide

## ✅ System Status
**Status:** Fully Operational
**Version:** 2.0 Enterprise
**Migration:** Applied (0015_add_enterprise_notification_fields)

---

## 📍 Quick Access

### For Users:
- **Notification Bell (Navbar)**: Click bell icon → View latest 10 notifications
- **Full Notification Center**: `/accounts/notifications/`
- **Admin Dashboard Card**: Available on admin home page

### For Developers:
- **Model**: `accounts.models.Notification`
- **Helper Functions**: `accounts.notifications.create_notification()`
- **Views**: `accounts.views_notifications.py`
- **Template**: `templates/accounts/notifications_list.html`

---

## 🎯 Features

### 1. **Multi-Level Classification**

**Priority Levels:**
- `urgent` - Red badge, requires immediate action
- `high` - Orange badge, important
- `normal` - Default
- `low` - Low priority

**Severity Levels:**
- `critical` 🚨 - Red color, critical issue
- `error` ❌ - Red color, error occurred
- `warning` ⚠️ - Yellow color, warning
- `success` ✅ - Green color, success message
- `info` ℹ️ - Blue color, informational

**Categories:**
- `operations` - Daily operations & coordination
- `billing` - Billing & invoicing
- `finance` - Financial matters
- `projects` - Project-related
- `system` - System notifications
- `reminder` - Reminders & alerts
- `alert` - General alerts

### 2. **Smart Features**

✅ **Action Buttons** - Direct links to relevant pages
✅ **Metadata** - Store custom JSON data
✅ **Grouping** - Group related notifications
✅ **Pinning** - Pin important notifications to top
✅ **Soft Delete** - Delete without losing data
✅ **Archiving** - Archive old notifications

### 3. **User Interface**

**Navbar Dropdown:**
- Shows last 10 notifications
- Real-time unread count
- Quick actions
- Auto-refresh every 5 seconds

**Notification Center:**
- Advanced filtering (category, priority, unread)
- Batch operations (select multiple)
- Stats dashboard
- Search & pagination

**Admin Dashboard Card:**
- Total/unread/urgent counts
- Latest 5 notifications
- Quick access button

---

## 💻 Usage Examples

### Creating a Simple Notification

```python
from accounts.notifications import create_notification

notif = create_notification(
    recipient=user,
    notification_type='system',
    title='Welcome to the System',
    message='Your account has been activated.',
    priority='normal',
    severity='success',
    category='system'
)
```

### Creating a Notification with Action

```python
notif = create_notification(
    recipient=coordinator,
    notification_type='billing_corrected',
    title='Billing Corrected',
    message='Your monthly billing was updated by the controller.',
    priority='high',
    severity='warning',
    category='billing',
    action_url=f'/operations/monthly-billing/{billing.id}/',
    action_label='View Billing',
    monthly_billing=billing,
    project=project,
    metadata={
        'editor': controller.get_full_name(),
        'edit_date': timezone.now().isoformat()
    }
)
```

### Creating Grouped Notifications

```python
# Create multiple related notifications
for manager in managers:
    create_notification(
        recipient=manager,
        notification_type='dispute_raised',
        title='New Dispute Raised',
        message=f'{coordinator.get_full_name()} raised a dispute',
        priority='high',
        severity='warning',
        category='operations',
        action_url=f'/operations/disputes/{dispute.id}/',
        action_label='View Dispute',
        dispute=dispute,
        project=project,
        group_key=f'dispute_{dispute.id}'  # Groups all related notifications
    )
```

### Batch Operations (Frontend)

Users can:
- Select multiple notifications (checkbox)
- Mark selected as read
- Delete selected
- Archive selected (future feature)

### Filtering Notifications

Available filters:
- By category (Operations, Billing, Finance, etc.)
- By priority (Urgent, High, Normal, Low)
- Unread only (toggle)

---

## 🔧 API Endpoints

### User Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/accounts/notifications/` | GET | Full notification list (HTML) |
| `/api/notifications/` | GET | JSON API (AJAX) |
| `/accounts/notifications/<id>/read/` | POST | Mark as read |
| `/accounts/notifications/<id>/delete/` | POST | Soft delete |
| `/accounts/notifications/mark-all-read/` | POST | Mark all as read |
| `/accounts/notifications/batch-action/` | POST | Batch operations |

### API Response Example

```json
{
  "notifications": [
    {
      "id": 15,
      "title": "Billing Corrected",
      "message": "Your billing was updated...",
      "priority": "high",
      "severity": "warning",
      "category": "billing",
      "is_read": false,
      "is_pinned": false,
      "icon": "⚠️",
      "color_class": "yellow",
      "action_url": "/operations/monthly-billing/123/",
      "action_label": "View Billing",
      "time_ago": "5 minutes ago"
    }
  ],
  "unread_count": 5
}
```

---

## 📊 Database Schema

### Notification Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `recipient` | ForeignKey | User receiving notification |
| `notification_type` | CharField | Type of notification |
| `title` | CharField | Notification title |
| `message` | TextField | Notification message |
| `priority` | CharField | low/normal/high/urgent |
| `severity` | CharField | info/success/warning/error/critical |
| `category` | CharField | operations/billing/finance/etc |
| `action_url` | CharField | Link to relevant page |
| `action_label` | CharField | Button text (e.g., "View Billing") |
| `metadata` | JSONField | Custom JSON data |
| `is_read` | BooleanField | Read status |
| `is_deleted` | BooleanField | Soft delete flag |
| `is_archived` | BooleanField | Archive flag |
| `is_pinned` | BooleanField | Pin to top |
| `created_at` | DateTimeField | Creation timestamp |
| `read_at` | DateTimeField | When marked as read |
| `group_key` | CharField | For grouping notifications |

### Related Objects

- `dispute` - ForeignKey to DisputeLog
- `project` - ForeignKey to ProjectCode
- `monthly_billing` - ForeignKey to MonthlyBilling

---

## 🧪 Testing

Run comprehensive tests:

```bash
python test_notifications.py
```

Tests include:
- ✅ Priority levels (low, normal, high, urgent)
- ✅ Severity levels (info, success, warning, error, critical)
- ✅ All 7 categories
- ✅ Action URLs and labels
- ✅ Metadata (JSON storage)
- ✅ Grouping functionality
- ✅ Mark as read
- ✅ Soft delete
- ✅ Pin/unpin
- ✅ Statistics

---

## 🎨 UI Components

### Priority Badges

- **URGENT** - Red background, white text
- **High** - Orange background, orange text
- **Normal** - No badge
- **Low** - No badge

### Severity Icons

- 🚨 Critical
- ❌ Error
- ⚠️ Warning
- ✅ Success
- ℹ️ Info

### Color Coding

Notifications are color-coded by severity:
- Critical/Error: Red border-left
- Warning: Yellow border-left
- Success: Green border-left
- Info: Blue border-left

---

## 📝 Best Practices

### 1. **Choose Appropriate Priority**

```python
# Urgent - Requires immediate action
priority='urgent'  # Missing data entries, critical errors

# High - Important but not urgent
priority='high'  # Billing corrections, disputes assigned

# Normal - Standard notifications
priority='normal'  # Disputes resolved, queries assigned

# Low - Informational only
priority='low'  # Daily summaries, system updates
```

### 2. **Choose Appropriate Severity**

```python
# Critical - System-critical issues
severity='critical'  # System failures, data corruption

# Error - Errors that need fixing
severity='error'  # Failed operations, validation errors

# Warning - Potential issues
severity='warning'  # Billing corrections, pending approvals

# Success - Positive outcomes
severity='success'  # Disputes resolved, approvals granted

# Info - Informational
severity='info'  # General updates, assignments
```

### 3. **Use Meaningful Categories**

Match category to the business area:
- Operations → `category='operations'`
- Billing → `category='billing'`
- Finance → `category='finance'`
- Projects → `category='projects'`

### 4. **Always Provide Action URLs**

```python
# Good - Users can take action immediately
action_url='/operations/monthly-billing/123/'
action_label='View Billing'

# Bad - No way to act on notification
action_url=None
```

### 5. **Use Metadata for Context**

```python
# Store additional context
metadata={
    'editor': 'John Doe',
    'editor_id': 42,
    'original_value': 1000,
    'new_value': 1200,
    'timestamp': timezone.now().isoformat()
}
```

### 6. **Group Related Notifications**

```python
# When notifying multiple users about the same event
group_key=f'dispute_{dispute.id}'
group_key=f'billing_{billing.id}'
group_key=f'project_{project.id}'
```

---

## 🚀 Performance Tips

1. **Use select_related()** when fetching notifications with related objects
2. **Limit queries** with slicing (e.g., `[:10]`)
3. **Use indexes** - All common queries are indexed
4. **Soft delete** instead of hard delete for audit trail
5. **Archive old notifications** periodically

---

## 🔐 Security

- ✅ Users can only see their own notifications
- ✅ All operations require authentication
- ✅ CSRF protection on all POST requests
- ✅ Soft delete preserves audit trail
- ✅ Related objects protected by cascading

---

## 📈 Future Enhancements (Planned)

- [ ] WebSocket real-time notifications
- [ ] Push notifications (web push API)
- [ ] Email digest (daily/weekly summaries)
- [ ] Notification preferences (per category)
- [ ] Advanced search
- [ ] Export notifications (CSV/PDF)
- [ ] Notification templates
- [ ] Scheduled notifications

---

## 🆘 Troubleshooting

### Notifications not appearing?

1. Check user is authenticated
2. Verify notification created successfully
3. Check `is_deleted=False` and `recipient` is correct
4. Clear browser cache

### Badge count not updating?

- Navbar polls every 5 seconds
- Manually refresh page
- Check browser console for errors

### Batch operations not working?

- Ensure JavaScript is enabled
- Check CSRF token is present
- Verify user has permission

---

## 📞 Support

For issues or questions:
- Check this guide first
- Review test script: `test_notifications.py`
- Check code comments in `accounts/models.py`
- Review implementation in `accounts/notifications.py`

---

**Last Updated:** February 14, 2026
**Version:** 2.0 Enterprise
**Status:** ✅ Production Ready
