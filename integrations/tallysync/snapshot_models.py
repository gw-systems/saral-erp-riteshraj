from django.db import models
from django.utils import timezone
from projects.models import ProjectCode


class ProjectFinancialSnapshot(models.Model):
    """
    Daily snapshot of project financials from Tally
    Updated automatically after each Tally sync (every 30 min via Celery)
    """
    project = models.ForeignKey(
        ProjectCode,
        on_delete=models.CASCADE,
        related_name='financial_snapshots'
    )
    snapshot_date = models.DateField(
        help_text="Date of this snapshot"
    )
    
    # Tally-sourced financials
    tally_revenue = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Total revenue from Tally Sales vouchers"
    )
    tally_expenses = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Total expenses from Tally Purchase vouchers"
    )
    tally_profit = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Revenue - Expenses"
    )
    tally_margin_pct = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="Profit / Revenue * 100"
    )
    
    # Receivables (Sales - Receipts)
    total_billed = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Total Sales vouchers"
    )
    total_received = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Total Receipt vouchers"
    )
    outstanding = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Billed - Received"
    )
    
    # Area efficiency
    contracted_area = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="From ProjectCard billable_area"
    )
    revenue_per_sqft = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Revenue / Contracted Area"
    )
    profit_per_sqft = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Profit / Contracted Area"
    )
    
    # Transaction counts
    sales_count = models.IntegerField(
        default=0,
        help_text="Number of Sales vouchers"
    )
    purchase_count = models.IntegerField(
        default=0,
        help_text="Number of Purchase vouchers"
    )
    receipt_count = models.IntegerField(
        default=0,
        help_text="Number of Receipt vouchers"
    )
    payment_count = models.IntegerField(
        default=0,
        help_text="Number of Payment vouchers"
    )
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        db_table = 'tallysync_project_financial_snapshot'
        unique_together = ('project', 'snapshot_date')
        indexes = [
            models.Index(fields=['project', 'snapshot_date']),
            models.Index(fields=['snapshot_date']),
            models.Index(fields=['last_updated']),
        ]
        ordering = ['-snapshot_date', 'project']
    
    def __str__(self):
        return f"{self.project.code} - {self.snapshot_date}"


class SalespersonSnapshot(models.Model):
    """
    Monthly snapshot of salesperson performance
    Aggregates all their projects' financial data
    """
    salesperson_name = models.CharField(max_length=200)
    snapshot_month = models.DateField(
        help_text="First day of the month"
    )
    
    # Project counts
    total_projects = models.IntegerField(default=0)
    active_projects = models.IntegerField(default=0)
    
    # Financial aggregates
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_expenses = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    avg_margin_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Receivables
    total_outstanding = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    # Performance metrics
    avg_revenue_per_project = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    avg_profit_per_project = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'tallysync_salesperson_snapshot'
        unique_together = ('salesperson_name', 'snapshot_month')
        indexes = [
            models.Index(fields=['salesperson_name', 'snapshot_month']),
            models.Index(fields=['snapshot_month']),
        ]
        ordering = ['-snapshot_month', 'salesperson_name']
    
    def __str__(self):
        return f"{self.salesperson_name} - {self.snapshot_month.strftime('%B %Y')}"