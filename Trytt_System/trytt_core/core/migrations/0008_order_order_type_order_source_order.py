from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_alter_session_coach_alter_session_session_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='order_type',
            field=models.CharField(
                choices=[
                    ('regular', '一般訂單'),
                    ('refund', '退費訂單'),
                    ('swap', '換課訂單'),
                ],
                default='regular',
                max_length=10,
                verbose_name='訂單類型',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='source_order',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='derived_orders',
                to='core.order',
                verbose_name='原始訂單',
            ),
        ),
    ]
