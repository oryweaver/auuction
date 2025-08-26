import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.management import call_command

from auctions.models import Auction, Category, Item

User = get_user_model()


@pytest.fixture
@pytest.mark.django_db
def base_objects():
    a = Auction.objects.create(year=2025, slug="auction-2025", title="Auction 2025")
    cat = Category.objects.create(name="Goods", slug="goods")
    donor = User.objects.create_user(username="donor@example.org", email="donor@example.org", password="p")
    item = Item.objects.create(
        auction=a,
        donor=donor,
        category=cat,
        type=Item.TYPE_GOOD,
        slug="gizmo",
        title="Gizmo",
        status=Item.STATUS_DRAFT,
        opening_min_bid="5.00",
        bid_increment="1.00",
    )
    return a, cat, donor, item


@pytest.mark.django_db
def test_only_manager_can_publish(client, base_objects):
    call_command("bootstrap_roles")
    a, cat, donor, item = base_objects

    # donor cannot publish
    client.post(reverse("auctions:login"), {"email": donor.email, "password": "p"})
    resp = client.post(reverse("auctions:manager_publish_item", kwargs={"slug": item.slug}), follow=True)
    assert resp.status_code == 200
    item.refresh_from_db()
    assert item.status == Item.STATUS_DRAFT

    # manager can publish
    manager = User.objects.create_user(username="m@example.org", email="m@example.org", password="p")
    from django.contrib.auth.models import Group

    manager_group = Group.objects.get(name="Manager")
    manager.groups.add(manager_group)
    client.post(reverse("auctions:login"), {"email": manager.email, "password": "p"})
    resp2 = client.post(reverse("auctions:manager_publish_item", kwargs={"slug": item.slug}), follow=True)
    assert resp2.status_code == 200
    item.refresh_from_db()
    assert item.status == Item.STATUS_PUBLISHED


@pytest.mark.django_db
def test_donor_cannot_edit_after_publish(client, base_objects):
    call_command("bootstrap_roles")
    a, cat, donor, item = base_objects
    # publish as manager
    manager = User.objects.create_user(username="m2@example.org", email="m2@example.org", password="p")
    from django.contrib.auth.models import Group

    manager_group = Group.objects.get(name="Manager")
    manager.groups.add(manager_group)
    client.post(reverse("auctions:login"), {"email": manager.email, "password": "p"})
    client.post(reverse("auctions:manager_publish_item", kwargs={"slug": item.slug}))

    # donor tries to edit -> redirected away
    client.post(reverse("auctions:login"), {"email": donor.email, "password": "p"})
    resp = client.get(reverse("auctions:donor_item_edit", kwargs={"slug": item.slug}))
    assert resp.status_code in (302, 301)
