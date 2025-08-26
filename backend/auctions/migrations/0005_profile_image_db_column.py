# Generated to ensure profile.image column exists in DB in environments where
# a prior migration added only state.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("auctions", "0004_item_at_church_item_location_address_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE auctions_profile "
                        "ADD COLUMN IF NOT EXISTS image varchar(100) NULL"
                    ),
                    reverse_sql=(
                        "ALTER TABLE auctions_profile "
                        "DROP COLUMN IF EXISTS image"
                    ),
                )
            ],
            state_operations=[],
        )
    ]
