import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.text import slugify

from auctions.models import Auction, Category, Item


@pytest.mark.django_db
def test_auction_str_and_unique_year():
    a1 = Auction.objects.create(year=2025, slug="auction-2025", title="TVUUC Auction 2025")
    assert str(a1) == "Auction 2025"
    with pytest.raises(IntegrityError):
        Auction.objects.create(year=2025, slug="dupe-2025", title="Dup")


@pytest.mark.django_db
def test_category_unique_slug_and_ordering():
    c1 = Category.objects.create(name="B", slug=slugify("B"), sort_order=2)
    c2 = Category.objects.create(name="A", slug=slugify("A"), sort_order=1)
    # Ensure the IntegrityError happens within its own atomic block so the test
    # transaction isn't left in a broken state.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Category.objects.create(name="C", slug=slugify("A"))
    names = list(Category.objects.values_list("name", flat=True))
    assert names == ["A", "B"]


@pytest.mark.django_db
def test_item_choices_validated_with_full_clean():
    a = Auction.objects.create(year=2026, slug="auction-2026", title="TVUUC Auction 2026")
    cat = Category.objects.create(name="Events", slug="events")
    item = Item(
        auction=a,
        category=cat,
        type=Item.TYPE_EVENT,
        slug="valid-item",
        title="Valid",
        status=Item.STATUS_DRAFT,
    )
    item.full_clean()  # should not raise
    item.save()

    bad = Item(
        auction=a,
        category=cat,
        type="nope",
        slug="bad-item",
        title="Bad",
        status=Item.STATUS_DRAFT,
    )
    with pytest.raises(ValidationError):
        bad.full_clean()


@pytest.mark.django_db
def test_item_unique_slug_constraint():
    a = Auction.objects.create(year=2027, slug="auction-2027", title="TVUUC Auction 2027")
    cat = Category.objects.create(name="Goods", slug="goods")
    Item.objects.create(auction=a, category=cat, type=Item.TYPE_GOOD, slug="dupe", title="One")
    with pytest.raises(IntegrityError):
        Item.objects.create(auction=a, category=cat, type=Item.TYPE_GOOD, slug="dupe", title="Two")
