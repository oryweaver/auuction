from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
import os

from .models import Auction, Category, Item, Bid, ProxyBid


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    list_display = ("year", "title", "state", "starts_at", "ends_at")
    search_fields = ("year", "title", "slug")
    list_filter = ("state",)
    prepopulated_fields = {"slug": ("title",)}

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "send-test-sms/",
                self.admin_site.admin_view(self.send_test_sms_view),
                name="auctions_auction_send_test_sms",
            ),
        ]
        return custom + urls

    def send_test_sms_view(self, request):
        """Render a simple form to send a test SMS using Telnyx."""
        context = {
            **self.admin_site.each_context(request),
            "title": "Send Test SMS",
            "opts": self.model._meta,
        }
        if request.method == "POST":
            to = (request.POST.get("to") or "").strip()
            text = (request.POST.get("text") or "Test from auction admin").strip()
            if not to:
                messages.error(request, "Destination 'to' is required (E.164 format)")
            else:
                api_key = os.environ.get("TELNYX_API_KEY")
                profile_id = os.environ.get("TELNYX_MESSAGING_PROFILE_ID")
                from_number = os.environ.get("TELNYX_FROM_NUMBER")
                if not api_key:
                    messages.error(request, "TELNYX_API_KEY is not configured")
                elif not (profile_id or from_number):
                    messages.error(
                        request, "TELNYX_MESSAGING_PROFILE_ID or TELNYX_FROM_NUMBER must be set"
                    )
                else:
                    try:
                        import telnyx

                        telnyx.api_key = api_key
                        if profile_id:
                            msg = telnyx.Message.create(
                                to=to,
                                messaging_profile_id=profile_id,
                                text=text,
                            )
                        else:
                            msg = telnyx.Message.create(
                                to=to,
                                from_=from_number,
                                text=text,
                            )
                        messages.success(
                            request, f"Sent. Message ID: {getattr(msg, 'id', None) or 'unknown'}"
                        )
                        return redirect("admin:auctions_auction_send_test_sms")
                    except Exception as e:
                        messages.error(request, f"Error sending SMS: {e}")
        return render(request, "admin/auctions/send_test_sms.html", context)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "sort_order")
    search_fields = ("name", "slug")
    list_filter = ("active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "auction", "category", "status", "quantity_total", "quantity_sold")
    list_filter = ("type", "status", "auction", "category")
    search_fields = ("title", "slug", "description")
    autocomplete_fields = ("auction", "category", "donor")
    prepopulated_fields = {"slug": ("title",)}


class BidInline(admin.TabularInline):
    model = Bid
    extra = 0
    autocomplete_fields = ("bidder",)
    fields = ("bidder", "amount", "idempotency_key", "created_at")
    readonly_fields = ("created_at",)


class ProxyBidInline(admin.TabularInline):
    model = ProxyBid
    extra = 0
    autocomplete_fields = ("bidder",)
    fields = ("bidder", "max_amount", "seats", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


# Attach inlines to Item admin for convenient per-item management
ItemAdmin.inlines = [ProxyBidInline, BidInline]


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ("item", "bidder", "amount", "created_at")
    list_filter = ("item",)
    search_fields = ("item__title", "item__slug", "bidder__username", "bidder__email")
    autocomplete_fields = ("item", "bidder")
    date_hierarchy = "created_at"
    list_select_related = ("item", "bidder")


@admin.register(ProxyBid)
class ProxyBidAdmin(admin.ModelAdmin):
    list_display = ("item", "bidder", "max_amount", "seats", "updated_at")
    list_filter = ("item",)
    search_fields = ("item__title", "item__slug", "bidder__username", "bidder__email")
    autocomplete_fields = ("item", "bidder")
    date_hierarchy = "updated_at"
    list_select_related = ("item", "bidder")
