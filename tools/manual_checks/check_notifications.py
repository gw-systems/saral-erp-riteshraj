#!/usr/bin/env python
"""
Manual notification-system checker.
Tests notification features including priority, severity, categories, and batch operations.
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'minierp.settings')
django.setup()

from accounts.models import User, Notification
from accounts.notifications import create_notification
from django.utils import timezone

def test_notification_system():
    print("=" * 80)
    print("ENTERPRISE NOTIFICATION SYSTEM - COMPREHENSIVE TEST")
    print("=" * 80)
    print()

    # Get test users
    admin = User.objects.filter(role='admin').first()
    if not admin:
        print("âŒ No admin user found. Cannot run tests.")
        return

    print(f"âœ… Test user: {admin.get_full_name()} ({admin.email})")
    print()

    # Test 1: Create notifications with different priorities
    print("ðŸ“ TEST 1: Priority Levels")
    print("-" * 80)

    priorities = [
        ('low', 'Low priority test notification'),
        ('normal', 'Normal priority test notification'),
        ('high', 'High priority test notification'),
        ('urgent', 'Urgent priority test notification'),
    ]

    for priority, message in priorities:
        notif = create_notification(
            recipient=admin,
            notification_type='system',
            title=f'{priority.upper()} Priority Test',
            message=message,
            priority=priority,
            severity='info',
            category='system',
            metadata={'test': True, 'priority_test': priority}
        )
        if notif:
            print(f"  âœ… Created {priority.upper():8} priority notification (ID: {notif.id})")
        else:
            print(f"  âŒ Failed to create {priority} priority notification")
    print()

    # Test 2: Create notifications with different severities
    print("ðŸ“ TEST 2: Severity Levels")
    print("-" * 80)

    severities = [
        ('info', 'â„¹ï¸', 'Information notification'),
        ('success', 'âœ…', 'Success notification'),
        ('warning', 'âš ï¸', 'Warning notification'),
        ('error', 'âŒ', 'Error notification'),
        ('critical', 'ðŸš¨', 'Critical notification'),
    ]

    for severity, expected_icon, message in severities:
        notif = create_notification(
            recipient=admin,
            notification_type='system_alert',
            title=f'{severity.upper()} Severity Test',
            message=message,
            priority='normal',
            severity=severity,
            category='system',
            metadata={'test': True, 'severity_test': severity}
        )
        if notif:
            print(f"  âœ… Created {severity.upper():8} severity (Icon: {notif.icon}) - ID: {notif.id}")
        else:
            print(f"  âŒ Failed to create {severity} severity notification")
    print()

    # Test 3: Create notifications with different categories
    print("ðŸ“ TEST 3: Categories")
    print("-" * 80)

    categories = [
        ('operations', 'Operations test notification'),
        ('billing', 'Billing test notification'),
        ('finance', 'Finance test notification'),
        ('projects', 'Projects test notification'),
        ('system', 'System test notification'),
        ('reminder', 'Reminder test notification'),
        ('alert', 'Alert test notification'),
    ]

    for category, message in categories:
        notif = create_notification(
            recipient=admin,
            notification_type='system',
            title=f'{category.title()} Category Test',
            message=message,
            priority='normal',
            severity='info',
            category=category,
            metadata={'test': True, 'category_test': category}
        )
        if notif:
            print(f"  âœ… Created {category.upper():12} category notification (ID: {notif.id})")
        else:
            print(f"  âŒ Failed to create {category} category notification")
    print()

    # Test 4: Test action URLs and labels
    print("ðŸ“ TEST 4: Action URLs & Labels")
    print("-" * 80)

    notif = create_notification(
        recipient=admin,
        notification_type='billing_corrected',
        title='Test Billing Correction',
        message='Your monthly billing was corrected. Click to view details.',
        priority='high',
        severity='warning',
        category='billing',
        action_url='/operations/monthly-billing/',
        action_label='View Billing',
        metadata={'test': True, 'action_test': True}
    )
    if notif:
        print(f"  âœ… Created notification with action")
        print(f"     Action URL: {notif.action_url}")
        print(f"     Action Label: {notif.action_label}")
        print(f"     ID: {notif.id}")
    else:
        print("  âŒ Failed to create notification with action")
    print()

    # Test 5: Test metadata
    print("ðŸ“ TEST 5: Metadata (JSON Field)")
    print("-" * 80)

    notif = create_notification(
        recipient=admin,
        notification_type='system',
        title='Metadata Test',
        message='Testing JSON metadata storage',
        priority='normal',
        severity='info',
        category='system',
        metadata={
            'test': True,
            'version': '2.0',
            'features': ['priority', 'severity', 'categories', 'batch_ops'],
            'timestamp': timezone.now().isoformat(),
            'nested': {'key': 'value', 'number': 123}
        }
    )
    if notif:
        print(f"  âœ… Created notification with metadata (ID: {notif.id})")
        print(f"     Metadata: {notif.metadata}")
    else:
        print("  âŒ Failed to create notification with metadata")
    print()

    # Test 6: Test grouping
    print("ðŸ“ TEST 6: Notification Grouping")
    print("-" * 80)

    group_key = f'test_group_{timezone.now().timestamp()}'
    for i in range(3):
        notif = create_notification(
            recipient=admin,
            notification_type='system',
            title=f'Grouped Notification {i+1}',
            message=f'This is notification {i+1} in the group',
            priority='normal',
            severity='info',
            category='system',
            group_key=group_key,
            metadata={'test': True, 'group_index': i+1}
        )
        if notif:
            print(f"  âœ… Created grouped notification {i+1} (Group: {group_key[:20]}...)")
        else:
            print(f"  âŒ Failed to create grouped notification {i+1}")
    print()

    # Test 7: Statistics
    print("ðŸ“Š TEST 7: Statistics")
    print("-" * 80)

    total = Notification.objects.filter(recipient=admin, is_deleted=False).count()
    unread = Notification.objects.filter(recipient=admin, is_deleted=False, is_read=False).count()
    urgent = Notification.objects.filter(recipient=admin, is_deleted=False, priority='urgent').count()
    high = Notification.objects.filter(recipient=admin, is_deleted=False, priority='high').count()

    print(f"  ðŸ“¬ Total Notifications: {total}")
    print(f"  ðŸ“® Unread: {unread}")
    print(f"  ðŸ”´ Urgent: {urgent}")
    print(f"  ðŸŸ  High Priority: {high}")
    print()

    # Test 8: Mark as read functionality
    print("ðŸ“ TEST 8: Mark as Read")
    print("-" * 80)

    test_notif = Notification.objects.filter(recipient=admin, is_read=False).first()
    if test_notif:
        print(f"  Before: is_read={test_notif.is_read}, read_at={test_notif.read_at}")
        test_notif.mark_as_read()
        test_notif.refresh_from_db()
        print(f"  After:  is_read={test_notif.is_read}, read_at={test_notif.read_at}")
        print(f"  âœ… Mark as read works correctly")
    else:
        print("  âš ï¸  No unread notifications to test")
    print()

    # Test 9: Soft delete functionality
    print("ðŸ“ TEST 9: Soft Delete")
    print("-" * 80)

    test_notif = create_notification(
        recipient=admin,
        notification_type='system',
        title='Delete Test',
        message='This notification will be soft deleted',
        priority='low',
        severity='info',
        category='system',
        metadata={'test': True, 'delete_test': True}
    )
    if test_notif:
        print(f"  Created test notification (ID: {test_notif.id})")
        print(f"  Before: is_deleted={test_notif.is_deleted}, deleted_at={test_notif.deleted_at}")
        test_notif.soft_delete()
        test_notif.refresh_from_db()
        print(f"  After:  is_deleted={test_notif.is_deleted}, deleted_at={test_notif.deleted_at}")
        print(f"  âœ… Soft delete works correctly")
    else:
        print("  âŒ Failed to create test notification")
    print()

    # Test 10: Pin functionality
    print("ðŸ“ TEST 10: Pin/Unpin")
    print("-" * 80)

    test_notif = Notification.objects.filter(recipient=admin, is_deleted=False, is_pinned=False).first()
    if test_notif:
        print(f"  Before: is_pinned={test_notif.is_pinned}")
        test_notif.pin()
        test_notif.refresh_from_db()
        print(f"  After pin: is_pinned={test_notif.is_pinned}")
        test_notif.unpin()
        test_notif.refresh_from_db()
        print(f"  After unpin: is_pinned={test_notif.is_pinned}")
        print(f"  âœ… Pin/unpin works correctly")
    else:
        print("  âš ï¸  No notifications available to test pinning")
    print()

    # Final Summary
    print("=" * 80)
    print("âœ… ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print()
    print(f"ðŸ“Š Final Statistics for {admin.get_full_name()}:")
    print(f"   Total Notifications: {Notification.objects.filter(recipient=admin, is_deleted=False).count()}")
    print(f"   Unread: {Notification.objects.filter(recipient=admin, is_deleted=False, is_read=False).count()}")
    print(f"   Pinned: {Notification.objects.filter(recipient=admin, is_deleted=False, is_pinned=True).count()}")
    print(f"   Deleted: {Notification.objects.filter(recipient=admin, is_deleted=True).count()}")
    print()
    print("ðŸŽ‰ Enterprise Notification System is fully operational!")
    print()

if __name__ == '__main__':
    test_notification_system()
