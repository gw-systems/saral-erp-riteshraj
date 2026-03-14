from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0005_add_expense_log_to_synclog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='synclog',
            name='integration',
            field=models.CharField(blank=True, choices=[('bigin', 'Bigin CRM'), ('gmail', 'Gmail Inbox'), ('gmail_leads', 'Gmail Leads'), ('google_ads', 'Google Ads'), ('callyzer', 'Callyzer'), ('tallysync', 'TallySync'), ('expense_log', 'Expense Log')], db_index=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='synclog',
            name='sync_type',
            field=models.CharField(choices=[('bigin_full', 'Bigin Full Sync'), ('bigin_incremental', 'Bigin Incremental Sync'), ('bigin_module', 'Bigin Module Sync'), ('gmail_full', 'Gmail Full Sync'), ('gmail_incremental', 'Gmail Incremental Sync'), ('gmail_leads_full', 'Gmail Leads Full Sync'), ('gmail_leads_incremental', 'Gmail Leads Incremental Sync'), ('google_ads', 'Google Ads Sync'), ('google_ads_historical', 'Google Ads Historical Sync'), ('callyzer', 'Callyzer Sync'), ('tally_full', 'Tally Full Sync'), ('tally_incremental', 'Tally Incremental Sync'), ('tally_companies', 'Tally Companies Sync'), ('tally_ledgers', 'Tally Ledgers Sync'), ('tally_vouchers', 'Tally Vouchers Sync'), ('expense_log_full', 'Expense Log Full Sync'), ('expense_log_incremental', 'Expense Log Incremental Sync')], db_index=True, max_length=50),
        ),
    ]
