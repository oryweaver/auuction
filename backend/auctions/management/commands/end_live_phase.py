from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.db.models import OuterRef, Subquery

from auctions.models import Auction, Item, Bid


class Command(BaseCommand):
    help = "End the live auction phase: optionally close the Auction and mark items with winning bids as sold."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group()
        g.add_argument("--auction", type=int, help="Auction year to close (e.g., 2025)")
        g.add_argument("--slug", type=str, help="Auction slug to close")
        parser.add_argument(
            "--close-auction",
            action="store_true",
            help="Also set Auction.state=CLOSED and ends_at=now",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without persisting",
        )
        parser.add_argument(
            "--verbose-items",
            action="store_true",
            help="List item-level status decisions",
        )

    def handle(self, *args, **options):
        year = options.get("auction")
        slug = options.get("slug")
        dry_run = options.get("dry_run", False)
        close_auction = options.get("close_auction", False)
        verbose_items = options.get("verbose_items", False)

        auction = None
        if year is not None:
            auction = Auction.objects.filter(year=year).first()
        elif slug:
            auction = Auction.objects.filter(slug=slug).first()
        else:
            auction = Auction.objects.order_by("-year").first()

        if not auction:
            raise CommandError("Auction not found. Provide --auction YEAR or --slug.")

        self.stdout.write(self.style.NOTICE(f"Target auction: {auction.year} (state={auction.state})"))

        # Items eligible to close: published and not fixed-price
        qs = Item.objects.filter(auction=auction, status=Item.STATUS_PUBLISHED).exclude(type=Item.TYPE_FIXED_PRICE)

        # Determine top bid per item
        top_bidder_sq = Bid.objects.filter(item=OuterRef("pk")).order_by("-amount", "-created_at").values("bidder_id")[:1]
        top_amount_sq = Bid.objects.filter(item=OuterRef("pk")).order_by("-amount", "-created_at").values("amount")[:1]

        items = (
            qs.select_related("category", "donor")
            .annotate(top_bidder_id=Subquery(top_bidder_sq), top_amount=Subquery(top_amount_sq))
            .order_by("title")
        )

        to_mark_sold = []
        to_leave_published = []

        for it in items:
            if it.top_bidder_id is not None and it.top_amount is not None:
                to_mark_sold.append(it)
                if verbose_items:
                    self.stdout.write(f"WIN: {it.title} -> SOLD at {it.top_amount}")
            else:
                to_leave_published.append(it)
                if verbose_items:
                    self.stdout.write(f"NO BIDS: {it.title} (remains Published for potential reoffer)")

        self.stdout.write(
            self.style.WARNING(
                f"Summary: {len(to_mark_sold)} to mark SOLD, {len(to_leave_published)} remain PUBLISHED"
            )
        )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run complete. No changes saved."))
            return

        with transaction.atomic():
            # Mark winners as SOLD
            if to_mark_sold:
                Item.objects.filter(pk__in=[i.pk for i in to_mark_sold]).update(status=Item.STATUS_SOLD)

            # Optionally close auction
            if close_auction:
                auction.state = Auction.CLOSED
                auction.ends_at = timezone.now()
                auction.save(update_fields=["state", "ends_at"])

        self.stdout.write(self.style.SUCCESS("Live phase end: updates applied."))
