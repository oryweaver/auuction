import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model

from auctions.models import Auction, Category, Item, Bid

User = get_user_model()


@pytest.mark.django_db
def test_place_first_bid_and_increment_rules(client):
    a = Auction.objects.create(year=2025, slug="auction-2025", title="Auction 2025")
    cat = Category.objects.create(name="Goods", slug="goods")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_GOOD,
        slug="lamp",
        title="Lamp",
        status=Item.STATUS_PUBLISHED,
        opening_min_bid=Decimal("10.00"),
    )
    user = User.objects.create_user(username="b@example.org", email="b@example.org", password="p")
    client.post(reverse("auctions:login"), {"email": user.email, "password": "p"})

    # too low for first bid (< opening_min_bid)
    resp = client.post(reverse("auctions:place_bid", kwargs={"slug": item.slug}), {"amount": "9.00"}, follow=True)
    assert resp.status_code == 200
    assert not Bid.objects.filter(item=item).exists()

    # first bid allowed at opening_min_bid
    resp2 = client.post(reverse("auctions:place_bid", kwargs={"slug": item.slug}), {"amount": "10.00"}, follow=True)
    assert resp2.status_code == 200
    b = Bid.objects.get(item=item)
    assert b.amount == Decimal("10.00")

    # next must be >= 11.00 (standard increment at 10 is 1)
    resp3 = client.post(reverse("auctions:place_bid", kwargs={"slug": item.slug}), {"amount": "10.50"}, follow=True)
    assert resp3.status_code == 200
    assert Bid.objects.filter(item=item).count() == 1

    resp4 = client.post(reverse("auctions:place_bid", kwargs={"slug": item.slug}), {"amount": "11.00"}, follow=True)
    assert resp4.status_code == 200
    assert Bid.objects.filter(item=item).count() == 2


@pytest.mark.django_db
def test_idempotent_bid_submission(client):
    a = Auction.objects.create(year=2026, slug="auction-2026", title="Auction 2026")
    cat = Category.objects.create(name="Goods", slug="goods")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_GOOD,
        slug="chair",
        title="Chair",
        status=Item.STATUS_PUBLISHED,
        opening_min_bid=Decimal("5.00"),
    )
    user = User.objects.create_user(username="c@example.org", email="c@example.org", password="p")
    client.post(reverse("auctions:login"), {"email": user.email, "password": "p"})

    idem = "abc123"
    # First submit
    r1 = client.post(
        reverse("auctions:place_bid", kwargs={"slug": item.slug}),
        {"amount": "6.00", "idempotency_key": idem},
        follow=True,
    )
    assert r1.status_code == 200
    assert Bid.objects.filter(item=item, bidder=user).count() == 1

    # Duplicate submit with same key -> no duplicate bid
    r2 = client.post(
        reverse("auctions:place_bid", kwargs={"slug": item.slug}),
        {"amount": "6.00", "idempotency_key": idem},
        follow=True,
    )
    assert r2.status_code == 200
    assert Bid.objects.filter(item=item, bidder=user).count() == 1
