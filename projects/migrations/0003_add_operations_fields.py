from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_alter_projectcode_options'),
    ]

    operations = [
        # Empty - columns already added manually to database
        migrations.RunSQL(
            sql="SELECT 1;",  # No-op SQL
            reverse_sql="SELECT 1;",
        ),
    ]