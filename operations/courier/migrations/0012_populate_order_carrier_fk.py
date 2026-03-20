from django.db import migrations

def populate_carrier_fk(apps, schema_editor):
    Order = apps.get_model('courier', 'Order')
    Courier = apps.get_model('courier', 'Courier')
    
    # Cache all couriers in a dict {name: id}
    couriers = {c.name: c.id for c in Courier.objects.all()}
    
    orders = Order.objects.exclude(selected_carrier__isnull=True).exclude(selected_carrier="")
    
    updates = []
    for order in orders:
        if order.selected_carrier in couriers:
            order.carrier_id = couriers[order.selected_carrier]
            updates.append(order)
    
    if updates:
        Order.objects.bulk_update(updates, ['carrier'])

def reverse_populate(apps, schema_editor):
    Order = apps.get_model('courier', 'Order')
    Order.objects.update(carrier=None)

class Migration(migrations.Migration):

    dependencies = [
        ('courier', '0011_order_carrier'),
    ]

    operations = [
        migrations.RunPython(populate_carrier_fk, reverse_populate),
    ]
