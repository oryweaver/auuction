import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model

from auctions.models import Auction, Category, Item, Signup

User = get_user_model()


@pytest.mark.django_db
def test_multi_quantity_signup_and_adjust_increase_within_capacity(client):
    a = Auction.objects.create(year=2029, slug="auction-2029", title="Auction 2029")
    cat = Category.objects.create(name="Events", slug="events")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_FIXED_PRICE,
        slug="picnic",
        title="Picnic",
        status=Item.STATUS_PUBLISHED,
        buy_now_price=Decimal("10.00"),
        quantity_total=5,
        quantity_sold=0,
    )
    u = User.objects.create_user(username="u@example.org", email="u@example.org", password="p")

    # signup for 2 seats
    client.post(reverse("auctions:login"), {"email": u.email, "password": "p"})
    client.post(
        reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}),
        {"quantity": 2},
        follow=True,
    )
    item.refresh_from_db()
    s = Signup.objects.get(item=item, user=u)
    assert not s.waitlisted and s.quantity == 2
    assert item.quantity_sold == 2

    # increase to 4 (within capacity)
    client.post(
        reverse("auctions:fixed_price_adjust", kwargs={"slug": item.slug}),
        {"quantity": 4},
        follow=True,
    )
    item.refresh_from_db()
    s.refresh_from_db()
    assert s.quantity == 4
    assert item.quantity_sold == 4


@pytest.mark.django_db
def test_adjust_increase_beyond_capacity_fails(client):
    a = Auction.objects.create(year=2030, slug="auction-2030", title="Auction 2030")
    cat = Category.objects.create(name="Events", slug="events")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_FIXED_PRICE,
        slug="yoga",
        title="Yoga",
        status=Item.STATUS_PUBLISHED,
        buy_now_price=Decimal("12.00"),
        quantity_total=3,
        quantity_sold=0,
    )
    u1 = User.objects.create_user(username="u1@example.org", email="u1@example.org", password="p")
    u2 = User.objects.create_user(username="u2@example.org", email="u2@example.org", password="p")

    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), {"quantity": 2})
    client.post(reverse("auctions:login"), {"email": u2.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), {"quantity": 1})

    item.refresh_from_db()
    s1 = Signup.objects.get(item=item, user=u1)
    assert item.quantity_sold == 3 and not s1.waitlisted

    # u1 tries to increase to 3 (needs +1) but capacity is full -> stays 2
    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_adjust", kwargs={"slug": item.slug}), {"quantity": 3})

    item.refresh_from_db(); s1.refresh_from_db()
    assert s1.quantity == 2
    assert item.quantity_sold == 3


@pytest.mark.django_db
def test_adjust_decrease_promotes_waitlist_fifo(client):
    a = Auction.objects.create(year=2031, slug="auction-2031", title="Auction 2031")
    cat = Category.objects.create(name="Events", slug="events")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_FIXED_PRICE,
        slug="dinner",
        title="Dinner",
        status=Item.STATUS_PUBLISHED,
        buy_now_price=Decimal("20.00"),
        quantity_total=4,
        quantity_sold=0,
    )
    u1 = User.objects.create_user(username="u1@example.org", email="u1@example.org", password="p")
    u2 = User.objects.create_user(username="u2@example.org", email="u2@example.org", password="p")
    u3 = User.objects.create_user(username="u3@example.org", email="u3@example.org", password="p")

    # u1 confirmed for 3, u2 confirmed for 1 -> full
    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), {"quantity": 3})
    client.post(reverse("auctions:login"), {"email": u2.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), {"quantity": 1})
    item.refresh_from_db(); assert item.quantity_sold == 4

    # u3 requests 2 -> waitlisted
    client.post(reverse("auctions:login"), {"email": u3.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), {"quantity": 2})
    w3 = Signup.objects.get(item=item, user=u3)
    assert w3.waitlisted and w3.quantity == 2

    # u1 decreases from 3 to 2 -> frees 1 seat, not enough to promote w3 (needs 2)
    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_adjust", kwargs={"slug": item.slug}), {"quantity": 2})
    item.refresh_from_db(); w3.refresh_from_db()
    assert item.quantity_sold == 3
    assert w3.waitlisted

    # u2 cancels -> frees 1 more seat -> now promote w3 (needs 2 total, now available)
    client.post(reverse("auctions:login"), {"email": u2.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_cancel", kwargs={"slug": item.slug}))

    item.refresh_from_db(); w3.refresh_from_db()
    assert not w3.waitlisted
    assert item.quantity_sold == 4


@pytest.mark.django_db
def test_waitlisted_user_adjusts_quantity_only_updates_record(client):
    a = Auction.objects.create(year=2032, slug="auction-2032", title="Auction 2032")
    cat = Category.objects.create(name="Events", slug="events")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_FIXED_PRICE,
        slug="coding",
        title="Coding",
        status=Item.STATUS_PUBLISHED,
        buy_now_price=Decimal("15.00"),
        quantity_total=1,
        quantity_sold=0,
    )
    u1 = User.objects.create_user(username="u1@example.org", email="u1@example.org", password="p")
    u2 = User.objects.create_user(username="u2@example.org", email="u2@example.org", password="p")

    # u1 confirmed, u2 waitlisted for 2
    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), {"quantity": 1})
    client.post(reverse("auctions:login"), {"email": u2.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), {"quantity": 2})

    w2 = Signup.objects.get(item=item, user=u2)
    assert w2.waitlisted and w2.quantity == 2

    # u2 adjusts to 1; still waitlisted; item sold unchanged
    client.post(reverse("auctions:fixed_price_adjust", kwargs={"slug": item.slug}), {"quantity": 1})
    item.refresh_from_db(); w2.refresh_from_db()
    assert w2.waitlisted and w2.quantity == 1
    assert item.quantity_sold == 1
