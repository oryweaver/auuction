from django.contrib import admin
from .models import Auction, Category, Item


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    list_display = ("year", "title", "state", "starts_at", "ends_at")
    search_fields = ("year", "title", "slug")
    list_filter = ("state",)
    prepopulated_fields = {"slug": ("title",)}


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
