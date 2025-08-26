from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auctions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="signup",
            name="quantity",
            field=models.PositiveIntegerField(default=1),
            preserve_default=True,
        ),
    ]
