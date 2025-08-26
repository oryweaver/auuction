import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model

from auctions.models import Auction, Category, Item, Signup

User = get_user_model()


@pytest.mark.django_db
def test_fixed_price_capacity_and_waitlist(client):
    a = Auction.objects.create(year=2027, slug="auction-2027", title="Auction 2027")
    cat = Category.objects.create(name="Events", slug="events")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_FIXED_PRICE,
        slug="cooking-class",
        title="Cooking Class",
        status=Item.STATUS_PUBLISHED,
        buy_now_price=Decimal("25.00"),
        quantity_total=2,
        quantity_sold=0,
    )

    u1 = User.objects.create_user(username="u1@example.org", email="u1@example.org", password="p")
    u2 = User.objects.create_user(username="u2@example.org", email="u2@example.org", password="p")
    u3 = User.objects.create_user(username="u3@example.org", email="u3@example.org", password="p")

    # first two signups confirmed
    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), follow=True)
    client.post(reverse("auctions:login"), {"email": u2.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), follow=True)
    item.refresh_from_db()
    assert item.quantity_sold == 2
    assert Signup.objects.filter(item=item, waitlisted=False).count() == 2

    # third is waitlisted
    client.post(reverse("auctions:login"), {"email": u3.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}), follow=True)
    assert Signup.objects.filter(item=item, waitlisted=True).count() == 1


@pytest.mark.django_db
def test_cancel_promotes_waitlist(client):
    a = Auction.objects.create(year=2028, slug="auction-2028", title="Auction 2028")
    cat = Category.objects.create(name="Events", slug="events")
    item = Item.objects.create(
        auction=a,
        category=cat,
        type=Item.TYPE_FIXED_PRICE,
        slug="wine-night",
        title="Wine Night",
        status=Item.STATUS_PUBLISHED,
        buy_now_price=Decimal("30.00"),
        quantity_total=1,
        quantity_sold=0,
    )
    u1 = User.objects.create_user(username="u1x@example.org", email="u1x@example.org", password="p")
    u2 = User.objects.create_user(username="u2x@example.org", email="u2x@example.org", password="p")

    # u1 confirmed, u2 waitlisted
    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}))
    client.post(reverse("auctions:login"), {"email": u2.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_signup", kwargs={"slug": item.slug}))

    assert Signup.objects.filter(item=item, waitlisted=False).count() == 1
    assert Signup.objects.filter(item=item, waitlisted=True).count() == 1

    # u1 cancels -> u2 promoted
    client.post(reverse("auctions:login"), {"email": u1.email, "password": "p"})
    client.post(reverse("auctions:fixed_price_cancel", kwargs={"slug": item.slug}), follow=True)

    item.refresh_from_db()
    assert item.quantity_sold == 1
    assert Signup.objects.filter(item=item, waitlisted=False, user=u2).exists()
    assert not Signup.objects.filter(item=item, waitlisted=True).exists()
