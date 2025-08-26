from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from auctions.models import Item


class Command(BaseCommand):
    help = "Create default user groups and permissions: Donor, Manager"

    def handle(self, *args, **options):
        donor_group, _ = Group.objects.get_or_create(name="Donor")
        manager_group, _ = Group.objects.get_or_create(name="Manager")

        # Assign basic model permissions to Manager on Item
        ct = ContentType.objects.get_for_model(Item)
        perms = Permission.objects.filter(content_type=ct, codename__in=[
            "add_item", "change_item", "view_item",
        ])
        manager_group.permissions.set(perms)
        manager_group.save()

        # Donor has add/view item; edits restricted in code to owner-only
        donor_perms = Permission.objects.filter(content_type=ct, codename__in=[
            "add_item", "view_item",
        ])
        donor_group.permissions.set(donor_perms)
        donor_group.save()

        self.stdout.write(self.style.SUCCESS("Groups ensured: Donor, Manager with permissions."))
