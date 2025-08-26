from django.db import models
from django.conf import settings
from django.db.models import Q


class Auction(models.Model):
    DRAFT = 'draft'
    OPEN = 'open'
    CLOSED = 'closed'
    REOFFER = 'reoffer'
    STATE_CHOICES = [
        (DRAFT, 'Draft'),
        (OPEN, 'Open for Bidding'),
        (CLOSED, 'Closed'),
        (REOFFER, 'Reoffer'),
    ]

    year = models.PositiveIntegerField(unique=True)
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    reoffer_starts_at = models.DateTimeField(null=True, blank=True)
    reoffer_ends_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=DRAFT)

    def __str__(self) -> str:
        return f"Auction {self.year}"


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(unique=True)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Item(models.Model):
    TYPE_EVENT = 'event'
    TYPE_GOOD = 'good'
    TYPE_SERVICE = 'service'
    TYPE_FIXED_PRICE = 'fixed'
    TYPE_CHOICES = [
        (TYPE_EVENT, 'Hosted Event'),
        (TYPE_GOOD, 'Good'),
        (TYPE_SERVICE, 'Service'),
        (TYPE_FIXED_PRICE, 'Fixed Price Signup'),
    ]

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_SOLD = 'sold'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_SOLD, 'Sold/Closed'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    auction = models.ForeignKey(Auction, on_delete=models.PROTECT, related_name='items')
    donor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='donated_items')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')

    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    restrictions = models.TextField(blank=True)
    # Live event location (applies primarily to events)
    at_church = models.BooleanField(default=False)
    location_name = models.CharField(max_length=200, blank=True)
    location_address = models.TextField(blank=True)
    image = models.ImageField(upload_to="items/", null=True, blank=True)

    opening_min_bid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bid_increment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    buy_now_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    quantity_total = models.PositiveIntegerField(default=1)
    quantity_sold = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class Bid(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='bids')
    bidder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bids')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'bidder', 'idempotency_key'],
                name='uniq_bid_idem_per_item_bidder',
                condition=Q(idempotency_key__isnull=False),
            )
        ]

    def __str__(self) -> str:
        return f"Bid {self.amount} on {self.item_id} by {self.bidder_id}"


class Signup(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='signups')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='signups')
    quantity = models.PositiveIntegerField(default=1)
    waitlisted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        unique_together = (("item", "user"),)

    def __str__(self) -> str:
        return f"Signup u={self.user_id} item={self.item_id} wl={self.waitlisted} quantity={self.quantity}"


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    image = models.ImageField(upload_to="avatars/", null=True, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address_line1 = models.CharField("Address line 1", max_length=200, blank=True)
    address_line2 = models.CharField("Address line 2", max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)

    def __str__(self) -> str:
        return f"Profile of {self.user_id}"
