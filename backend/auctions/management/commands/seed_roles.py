from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

GROUPS = [
    ("Manager", "Managers can publish items and run the auction"),
    ("Donor", "Donors can submit and edit their draft items"),
]

class Command(BaseCommand):
    help = "Create default auth groups (Manager, Donor). Safe to run multiple times."

    def handle(self, *args, **options):
        created = []
        for name, _desc in GROUPS:
            g, was_created = Group.objects.get_or_create(name=name)
            if was_created:
                created.append(name)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created groups: {', '.join(created)}"))
        else:
            self.stdout.write("Groups already exist; nothing to do.")
