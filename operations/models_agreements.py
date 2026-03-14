"""
Agreement Renewal and Escalation Tracking Models
Manages workflow for renewals and annual escalations
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import User


# ==================== ESCALATION TRACKER ====================
class EscalationTracker(models.Model):
    """
    Track yearly escalation process
    Similar workflow to renewal but for rate escalations
    """
    
    project_card = models.ForeignKey(
        'ProjectCard',
        on_delete=models.CASCADE,
        related_name='escalation_trackers',
        help_text="Project card being escalated"
    )
    
    escalation_year = models.IntegerField(
        help_text="Which escalation (1 = 1st escalation after 1 year, 2 = 2nd after 2 years, etc.)"
    )
    escalation_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Escalation % (if fixed). NULL if mutually agreed."
    )
    
    # ==================== EMAIL TRACKING ====================
    initial_intimation_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when initial intimation email was sent"
    )
    first_reminder_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when 1st reminder was sent"
    )
    second_reminder_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when 2nd reminder was sent"
    )
    final_notice_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when final notice was sent"
    )
    
    # ==================== SALES MANAGER ====================
    sales_manager_informed_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when sales manager was informed"
    )
    sales_manager_notes = models.TextField(
        blank=True,
        help_text="Notes from sales manager interaction"
    )
    
    # ==================== FINANCE TEAM ====================
    finance_team_informed_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when finance team was informed"
    )
    finance_team_notes = models.TextField(
        blank=True,
        help_text="Notes from finance team interaction"
    )
    
    # ==================== CLIENT RESPONSE ====================
    client_acknowledged = models.BooleanField(
        default=False,
        help_text="Whether client has acknowledged the escalation"
    )
    client_acknowledgment_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when client acknowledged"
    )
    client_response_notes = models.TextField(
        blank=True,
        help_text="Client's response or feedback"
    )
    
    # ==================== STATUS ====================
    status = models.ForeignKey(
    'dropdown_master_data.EscalationStatus',
    on_delete=models.PROTECT,
    db_column='status',
    to_field='code',
    default='pending'
    )
    remarks = models.TextField(
        blank=True,
        help_text="Internal remarks"
    )
    
    # ==================== ESCALATION COMPLETION ====================
    escalation_applied_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when escalation was actually applied"
    )
    applied_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual % applied (for mutually agreed cases)"
    )
    
    # ==================== AUDIT FIELDS ====================
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='escalation_trackers_created',
        null=True,
        blank=True,
    )
    last_updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='escalation_trackers_updated'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'operations_escalationtracker'
        ordering = ['-escalation_year', '-created_at']
        unique_together = ['project_card', 'escalation_year']
        verbose_name = 'Escalation Tracker'
        verbose_name_plural = 'Escalation Trackers'
    
    def __str__(self):
        return f"Year {self.escalation_year} - {self.project_card.project.project_code} ({self.status})"
    
    @property
    def escalation_effective_date(self):
        """
        Calculate when this escalation should be effective
        Uses relativedelta for proper date handling (leap years, etc.)
        """
        if not self.project_card.agreement_start_date:
            return None
        
        from dateutil.relativedelta import relativedelta
        return self.project_card.agreement_start_date + relativedelta(years=self.escalation_year)
    
    @property
    def is_overdue(self):
        """Check if escalation is overdue"""
        if self.status.code == 'escalation_applied':
            return False

        escalation_date = self.escalation_effective_date
        if not escalation_date:
            return False
        
        return escalation_date < timezone.now().date()
    
    @property
    def days_overdue(self):
        """Calculate how many days overdue"""
        if not self.is_overdue:
            return 0
        
        escalation_date = self.escalation_effective_date
        return (timezone.now().date() - escalation_date).days
    
    @property
    def days_until_due(self):
        """Calculate days until escalation is due (negative if overdue)"""
        escalation_date = self.escalation_effective_date
        if not escalation_date:
            return None
        
        delta = (escalation_date - timezone.now().date()).days
        return delta
    
    def get_next_action(self):
        """
        Determine next action needed with time-based checks
        Returns tuple: (action_text, is_urgent)
        """
        from datetime import timedelta
        
        today = timezone.now().date()
        
        # If already applied, no action needed
        if self.status.code == 'escalation_applied':
            return ("Escalation Complete ✓", False)
        
        escalation_date = self.escalation_effective_date
        if not escalation_date:
            return ("ERROR: No agreement start date", True)
        
        days_until = self.days_until_due
        
        # Check if escalation date has passed (OVERDUE)
        if self.is_overdue:
            if self.status.code == 'pending':
                return (f"🚨 OVERDUE: Send Initial Intimation ({self.days_overdue} days late)", True)
            else:
                return (f"🚨 OVERDUE: Complete escalation process ({self.days_overdue} days late)", True)
        
        # Initial email (start 30 days before)
        if not self.initial_intimation_sent:
            if days_until <= 30:
                return ("Send Initial Intimation", False)
            else:
                return (f"Wait until {(escalation_date - timedelta(days=30)).strftime('%d %b %Y')} to start", False)
        
        # First reminder (3 days after initial)
        if not self.first_reminder_sent:
            days_since_initial = (today - self.initial_intimation_sent).days
            if days_since_initial >= 3:
                return ("Send 1st Reminder", False)
            else:
                wait_days = 3 - days_since_initial
                return (f"Wait {wait_days} day(s) before 1st reminder", False)
        
        # Second reminder (3 days after first)
        if not self.second_reminder_sent:
            days_since_first = (today - self.first_reminder_sent).days
            if days_since_first >= 3:
                return ("Send 2nd Reminder", False)
            else:
                wait_days = 3 - days_since_first
                return (f"Wait {wait_days} day(s) before 2nd reminder", False)
        
        # Inform sales manager
        if not self.sales_manager_informed_date:
            return ("Inform Sales Manager", False)
        
        # Final notice (3 days after sales informed)
        if not self.final_notice_sent:
            days_since_sales = (today - self.sales_manager_informed_date).days
            if days_since_sales >= 3:
                return ("Send Final Notice", False)
            else:
                wait_days = 3 - days_since_sales
                return (f"Wait {wait_days} day(s) before final notice", False)
        
        # Inform finance team
        if not self.finance_team_informed_date:
            return ("Inform Finance Team", True)
        
        return ("All reminders sent - Awaiting client acknowledgment", False)
    
    def get_workflow_stage(self):
        """Get current workflow stage for display"""
        if self.status.code == 'escalation_applied':
            return 'completed'
        elif self.status.code == 'disputed':
            return 'disputed'
        elif self.status.code == 'cancelled':
            return 'cancelled'
        elif self.finance_team_informed_date:
            return 'final_stage'
        elif self.final_notice_sent:
            return 'final_notice'
        elif self.sales_manager_informed_date:
            return 'sales_involved'
        elif self.second_reminder_sent:
            return 'reminder_2'
        elif self.first_reminder_sent:
            return 'reminder_1'
        elif self.initial_intimation_sent:
            return 'initial_sent'
        else:
            return 'not_started'


# ==================== ESCALATION LOG ====================
class EscalationLog(models.Model):
    """
    Audit log for escalation tracker actions
    Records every action taken during escalation process
    """

    tracker = models.ForeignKey(
        EscalationTracker,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    
    action_type = models.ForeignKey(
    'dropdown_master_data.EscalationActionType',
    on_delete=models.PROTECT,
    db_column='action_type',
    to_field='code'
    )
    action_date = models.DateField(
        help_text="Date when action was performed"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about the action"
    )
    
    # Email details (if applicable)
    email_sent_to = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Email recipients (comma-separated)"
    )
    email_subject = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Email subject line"
    )
    
    performed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='escalation_logs',
        help_text="User who performed this action"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        db_table = 'operations_escalationlog'
        ordering = ['-action_date', '-created_at']
        verbose_name = 'Escalation Log'
        verbose_name_plural = 'Escalation Logs'
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.tracker.project_card.project.project_code} - {self.action_date}"


# ==================== AGREEMENT RENEWAL TRACKER ====================
class AgreementRenewalTracker(models.Model):
    """
    Track agreement renewal process with email reminders
    Similar workflow to escalation but for full agreement renewals
    """
    
    project_card = models.ForeignKey(
        'ProjectCard',
        on_delete=models.CASCADE,
        related_name='renewal_trackers',
        help_text="Project card being renewed"
    )
    
    # ==================== EMAIL TRACKING ====================
    initial_email_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when initial renewal email was sent"
    )
    first_reminder_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when 1st reminder was sent"
    )
    second_reminder_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when 2nd reminder was sent"
    )
    third_reminder_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when 3rd reminder was sent"
    )
    final_intimation_sent = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when final intimation was sent"
    )
    
    # ==================== SALES MANAGER ====================
    sales_manager_informed_1_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when sales manager was informed (1st time)"
    )
    sales_manager_informed_1_notes = models.TextField(
        blank=True,
        help_text="Notes from first sales manager interaction"
    )
    sales_manager_informed_2_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when sales manager was informed (2nd time)"
    )
    sales_manager_informed_2_notes = models.TextField(
        blank=True,
        help_text="Notes from second sales manager interaction"
    )
    
    # ==================== CLIENT RESPONSE ====================
    client_responded = models.BooleanField(
        default=False,
        help_text="Whether client has responded to renewal"
    )
    client_response_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when client responded"
    )
    client_response_summary = models.TextField(
        blank=True,
        help_text="Summary of client's response"
    )
    
    # ==================== STATUS ====================
    status = models.ForeignKey(
    'dropdown_master_data.RenewalStatus',
    on_delete=models.PROTECT,
    db_column='status',
    to_field='code',
    default='pending'
    )
    remarks = models.TextField(
        blank=True,
        help_text="Internal remarks"
    )
    
    # ==================== RENEWAL COMPLETION ====================
    renewal_completed_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Date when renewal was completed"
    )
    
    # ==================== AUDIT FIELDS ====================
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='renewal_trackers_created',
        null=True,
        blank=True,
    )
    last_updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='renewal_trackers_updated'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'operations_agreementrenewaltracker'
        ordering = ['-created_at']
        verbose_name = 'Agreement Renewal Tracker'
        verbose_name_plural = 'Agreement Renewal Trackers'
    
    def __str__(self):
        return f"Renewal - {self.project_card.project.project_code} ({self.status})"
    
    @property
    def renewal_due_date(self):
        """Calculate when renewal is due (agreement end date)"""
        return self.project_card.agreement_end_date
    
    @property
    def is_overdue(self):
        """Check if renewal is overdue"""
        if self.status.code in ['renewed', 'not_renewed', 'cancelled']:
            return False

        due_date = self.renewal_due_date
        if not due_date:
            return False
        
        return due_date < timezone.now().date()
    
    @property
    def days_overdue(self):
        """Calculate how many days overdue"""
        if not self.is_overdue:
            return 0
        
        return (timezone.now().date() - self.renewal_due_date).days
    
    @property
    def days_until_due(self):
        """Calculate days until renewal is due"""
        due_date = self.renewal_due_date
        if not due_date:
            return None
        
        return (due_date - timezone.now().date()).days
    
    def get_next_action(self):
        """Determine next action needed"""
        from datetime import timedelta
        
        today = timezone.now().date()
        
        if self.status.code in ['renewed', 'not_renewed']:
            return ("Renewal Process Complete ✓", False)

        if self.status.code == 'cancelled':
            return ("Renewal Cancelled", False)
        
        due_date = self.renewal_due_date
        if not due_date:
            return ("ERROR: No agreement end date", True)
        
        days_until = self.days_until_due
        
        # OVERDUE
        if self.is_overdue:
            return (f"🚨 OVERDUE: Complete renewal process ({self.days_overdue} days late)", True)
        
        # Initial email (60 days before)
        if not self.initial_email_sent:
            if days_until <= 60:
                return ("Send Initial Renewal Email", False)
            else:
                return (f"Wait until {(due_date - timedelta(days=60)).strftime('%d %b %Y')} to start", False)
        
        # First reminder (3 days)
        if not self.first_reminder_sent:
            days_since = (today - self.initial_email_sent).days
            if days_since >= 3:
                return ("Send 1st Reminder", False)
            return (f"Wait {3 - days_since} day(s) before 1st reminder", False)
        
        # Second reminder (3 days)
        if not self.second_reminder_sent:
            days_since = (today - self.first_reminder_sent).days
            if days_since >= 3:
                return ("Send 2nd Reminder", False)
            return (f"Wait {3 - days_since} day(s) before 2nd reminder", False)
        
        # Third reminder + inform sales
        if not self.third_reminder_sent:
            days_since = (today - self.second_reminder_sent).days
            if days_since >= 3:
                return ("Send 3rd Reminder + Inform Sales Manager", False)
            return (f"Wait {3 - days_since} day(s) before 3rd reminder", False)
        
        # Final intimation
        if not self.final_intimation_sent:
            days_since = (today - self.third_reminder_sent).days
            if days_since >= 3:
                return ("Send Final Intimation to Accounts + Operations", True)
            return (f"Wait {3 - days_since} day(s) before final intimation", False)
        
        return ("All reminders sent - Awaiting client response", False)
    
    def get_workflow_stage(self):
        """Get current workflow stage"""
        if self.status.code == 'renewed':
            return 'completed'
        elif self.status.code in ['not_renewed', 'cancelled']:
            return 'closed'
        elif self.final_intimation_sent:
            return 'final_intimation'
        elif self.third_reminder_sent:
            return 'reminder_3'
        elif self.second_reminder_sent:
            return 'reminder_2'
        elif self.first_reminder_sent:
            return 'reminder_1'
        elif self.initial_email_sent:
            return 'initial_sent'
        else:
            return 'not_started'


# ==================== AGREEMENT RENEWAL LOG ====================
class AgreementRenewalLog(models.Model):
    """
    Audit log for renewal tracker actions
    Records every action taken during renewal process
    """
    
    tracker = models.ForeignKey(
        AgreementRenewalTracker,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    
    action_type = models.ForeignKey(
    'dropdown_master_data.RenewalActionType',
    on_delete=models.PROTECT,
    db_column='action_type',
    to_field='code'
    )
    action_date = models.DateField(
        help_text="Date when action was performed"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about the action"
    )
    
    # Email details (if applicable)
    email_sent_to = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Email recipients (comma-separated)"
    )
    email_subject = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Email subject line"
    )
    
    performed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='renewal_logs',
        help_text="User who performed this action"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        db_table = 'operations_agreementrenewallog'
        ordering = ['-action_date', '-created_at']
        verbose_name = 'Agreement Renewal Log'
        verbose_name_plural = 'Agreement Renewal Logs'
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.tracker.project_card.project.project_code} - {self.action_date}"