import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from auctions.models import Auction, Category, Item

User = get_user_model()


@pytest.fixture
@pytest.mark.django_db
def base_data():
    a = Auction.objects.create(year=2025, slug="auction-2025", title="Auction 2025")
    cat = Category.objects.create(name="Events", slug="events")
    return a, cat


@pytest.mark.django_db
def test_create_requires_login(client, base_data):
    resp = client.get(reverse("auctions:donor_item_create"))
    assert resp.status_code in (302, 301)


@pytest.mark.django_db
def test_donor_can_create_draft_item(client, base_data):
    a, cat = base_data
    user = User.objects.create_user(
        username="donor@example.org", email="donor@example.org", password="secret12345"
    )
    client.post(reverse("auctions:login"), {"email": "donor@example.org", "password": "secret12345"})

    resp = client.post(
        reverse("auctions:donor_item_create"),
        {
            "title": "Pasta Dinner",
            "type": Item.TYPE_EVENT,
            "category": cat.id,
            "description": "Dinner for 6",
            "opening_min_bid": "10.00",
            "bid_increment": "2.00",
            "quantity_total": 1,
        },
        follow=True,
    )
    assert resp.status_code == 200
    item = Item.objects.get(title="Pasta Dinner")
    assert item.status == Item.STATUS_DRAFT
    assert item.donor == user
    assert item.auction == a  # latest auction


@pytest.mark.django_db
def test_non_owner_cannot_edit(client, base_data):
    a, cat = base_data
    owner = User.objects.create_user(username="o@example.org", email="o@example.org", password="p")
    other = User.objects.create_user(username="x@example.org", email="x@example.org", password="p")
    item = Item.objects.create(
        auction=a,
        donor=owner,
        category=cat,
        type=Item.TYPE_GOOD,
        slug="thing",
        title="Thing",
        status=Item.STATUS_DRAFT,
        opening_min_bid="5.00",
        bid_increment="1.00",
    )

    client.post(reverse("auctions:login"), {"email": "x@example.org", "password": "p"})
    resp = client.get(reverse("auctions:donor_item_edit", kwargs={"slug": item.slug}))
    # redirected away
    assert resp.status_code in (302, 301)


@pytest.mark.django_db
def test_validations_enforced_by_type(client, base_data):
    a, cat = base_data
    user = User.objects.create_user(
        username="donor2@example.org", email="donor2@example.org", password="p"
    )
    client.post(reverse("auctions:login"), {"email": "donor2@example.org", "password": "p"})

    # Missing required fields for bidding type
    resp = client.post(
        reverse("auctions:donor_item_create"),
        {
            "title": "Incomplete Bid Item",
            "type": Item.TYPE_GOOD,
            "category": cat.id,
            "description": "",
            # opening_min_bid and bid_increment omitted
        },
    )
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Required for bidding items." in content

    # Fixed price requires buy_now_price and quantity
    resp2 = client.post(
        reverse("auctions:donor_item_create"),
        {
            "title": "Shirts",
            "type": Item.TYPE_FIXED_PRICE,
            "category": cat.id,
            "buy_now_price": "",
            "quantity_total": "",
        },
    )
    assert resp2.status_code == 200
    c2 = resp2.content.decode()
    assert "Required for fixed price items." in c2
