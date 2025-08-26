import pytest
from django.core.management import call_command
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from auctions.models import Item


@pytest.mark.django_db
def test_bootstrap_roles_creates_groups_and_permissions():
    # Ensure clean start
    Group.objects.filter(name__in=["Donor", "Manager"]).delete()
    call_command("bootstrap_roles")

    donor = Group.objects.get(name="Donor")
    manager = Group.objects.get(name="Manager")

    ct = ContentType.objects.get_for_model(Item)
    manager_perms = set(
        Permission.objects.filter(content_type=ct, codename__in=["add_item", "change_item", "view_item"]).values_list(
            "codename", flat=True
        )
    )
    assert manager_perms == {"add_item", "change_item", "view_item"}
    assert set(manager.permissions.values_list("codename", flat=True)) == manager_perms

    donor_perms = set(
        Permission.objects.filter(content_type=ct, codename__in=["add_item", "view_item"]).values_list(
            "codename", flat=True
        )
    )
    assert set(donor.permissions.values_list("codename", flat=True)) == donor_perms


@pytest.mark.django_db
def test_register_adds_user_to_donor_group(client):
    call_command("bootstrap_roles")
    # Register
    resp = client.post(
        reverse("auctions:register"),
        {
            "email": "donor@example.org",
            "first_name": "Don",
            "last_name": "Or",
            "password": "secret12345",
            "password_confirm": "secret12345",
        },
        follow=True,
    )
    assert resp.status_code == 200
    donor_group = Group.objects.get(name="Donor")
    assert donor_group.user_set.filter(email__iexact="donor@example.org").exists()


@pytest.mark.django_db
def test_manager_views_access_control(client, django_user_model):
    # Ensure roles exist
    call_command("bootstrap_roles")

    # Create users
    user = django_user_model.objects.create_user(email="user@example.org", password="pw12345")
    manager = django_user_model.objects.create_user(email="manager@example.org", password="pw12345")
    mgr_group = Group.objects.get(name="Manager")
    mgr_group.user_set.add(manager)

    # manager_home requires manager
    url_home = reverse("auctions:manager_home")
    # unauth -> redirect to login
    resp = client.get(url_home)
    assert resp.status_code in (302, 301)
    # non-manager authed -> redirected with message
    client.login(email="user@example.org", password="pw12345")
    resp = client.get(url_home, follow=False)
    assert resp.status_code in (302, 301)
    client.logout()
    # manager authed -> 200
    client.login(email="manager@example.org", password="pw12345")
    resp = client.get(url_home)
    assert resp.status_code == 200

    # manager_publish_item requires manager
    # Create a draft item
    from auctions.models import Auction, Item, Category
    auc = Auction.objects.create(year=2099, slug="2099", title="Test")
    cat = Category.objects.create(name="X", slug="x")
    item = Item.objects.create(auction=auc, donor=manager, category=cat, type=Item.TYPE_GOOD, slug="i1", title="i1")
    url_pub = reverse("auctions:manager_publish_item", kwargs={"slug": item.slug})

    client.logout()
    resp = client.get(url_pub)
    assert resp.status_code in (302, 301)
    client.login(email="user@example.org", password="pw12345")
    resp = client.get(url_pub)
    assert resp.status_code in (302, 301)
    client.logout()
    client.login(email="manager@example.org", password="pw12345")
    resp = client.get(url_pub, follow=True)
    assert resp.status_code == 200
    item.refresh_from_db()
    assert item.status == Item.STATUS_PUBLISHED
