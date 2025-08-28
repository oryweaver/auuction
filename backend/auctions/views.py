from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Prefetch, Sum, Q, OuterRef, Subquery
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.db import transaction, IntegrityError
from decimal import Decimal
from .models import Item, Category, Auction, Signup, Profile
from django.contrib.auth.models import Group
from .forms import RegisterForm, EmailLoginForm, DonorItemForm, ProfileForm, ManagerItemApprovalForm
from .utils import unique_slug, is_manager, standard_increment, manager_required


def catalog_list(request):
    q = (request.GET.get("q") or "").strip()
    categories = Category.objects.filter(active=True).order_by("sort_order", "name")
    items = (
        Item.objects.select_related("auction", "category")
        .filter(status=Item.STATUS_PUBLISHED)
        .order_by("title")
    )
    if q:
        items = items.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(restrictions__icontains=q)
            | Q(category__name__icontains=q)
        )
        categories = categories.filter(items__in=items).distinct()
    # Prefetch items per category for simple grouped display
    categories = categories.prefetch_related(
        Prefetch(
            "items",
            queryset=items,
            to_attr="published_items",
        )
    )
    ctx = {"categories": categories, "q": q}
    if q:
        try:
            ctx["results_count"] = items.count()
        except Exception:
            ctx["results_count"] = None
    return render(request, "auctions/catalog_list.html", ctx)


def item_detail(request, slug):
    item = get_object_or_404(
        Item.objects.select_related("auction", "category"), slug=slug
    )
    # compute context flags
    manager_can_publish = is_manager(request.user) and item.status == Item.STATUS_DRAFT
    can_bid = (
        item.status == Item.STATUS_PUBLISHED and item.type in (Item.TYPE_GOOD, Item.TYPE_SERVICE, Item.TYPE_EVENT)
    )
    can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
    user_signup = None
    if request.user.is_authenticated and can_signup:
        from .models import Signup  # local import to avoid cycles at import time
        try:
            user_signup = Signup.objects.filter(item=item, user=request.user).first()
        except Exception:
            # Likely migrations missing for Signup in this environment
            user_signup = None
    top_bid = None
    bid_seats_total = None
    bid_seats_available = None
    if can_bid:
        try:
            top_bid = item.bids.order_by("-amount", "-created_at").first()
        except Exception:
            top_bid = None
        # Show available seats without a bid yet (proxies placed)
        try:
            from .models import ProxyBid  # local import
            bid_seats_total = max(1, int(item.quantity_total or 1))
            # Sum of requested seats across all proxies
            proxies = ProxyBid.objects.filter(item=item).values("seats")
            requested = 0
            for row in proxies:
                requested += max(1, int(row.get("seats") or 1))
            bid_seats_available = max(0, bid_seats_total - requested)
        except Exception:
            bid_seats_total = None
            bid_seats_available = None
    # compute spots left for fixed-price items
    spots_left = 0
    try:
        qty_total = item.quantity_total or 0
        qty_sold = item.quantity_sold or 0
        spots_left = max(0, qty_total - qty_sold)
    except Exception:
        spots_left = 0
    ctx = {
        "item": item,
        "manager_can_publish": manager_can_publish,
        "can_bid": can_bid,
        "can_signup": can_signup,
        "user_signup": user_signup,
        "top_bid": top_bid,
        "spots_left": spots_left,
        "bid_seats_total": bid_seats_total,
        "bid_seats_available": bid_seats_available,
    }
    return render(request, "auctions/item_detail.html", ctx)


@login_required
def place_bid(request, slug):
    if request.method != "POST":
        return redirect("auctions:item_detail", slug=slug)
    item = get_object_or_404(Item.objects.select_related("auction"), slug=slug)
    if item.status != Item.STATUS_PUBLISHED or item.type == Item.TYPE_FIXED_PRICE:
        messages.error(request, "Bidding is not allowed on this item.")
        return redirect("auctions:item_detail", slug=item.slug)

    # Parse inputs: max amount (proxy max) and optional quantity
    raw_amount = (request.POST.get("amount") or "").strip()
    try:
        max_amount = Decimal(raw_amount)
    except Exception:
        messages.error(request, "Enter a valid bid amount.")
        return redirect("auctions:item_detail", slug=item.slug)
    try:
        req_seats = int((request.POST.get("quantity") or "1").strip() or "1")
    except Exception:
        req_seats = 1
    K_total = max(1, int(item.quantity_total or 1))
    req_seats = max(1, min(req_seats, K_total))

    # Helpers for proxy bidding
    def get_increment(base: Decimal) -> Decimal:
        return item.bid_increment if item.bid_increment is not None else standard_increment(base)

    def compute_current_state(locked_item):
        """Compute uniform-price outcome for multi-quantity items with seat-demand.

        Returns (top_bidder, public_price, is_full, winners_map)
        - Expand each proxy bid into `seats` unit-demand slots with same (max_amount, updated_at, bidder_id)
        - Sort units by (-max_amount, updated_at asc).
        - K = item.quantity_total (>=1)
        - If #units <= K: price = opening, is_full=False, winners are all units.
        - Else: price = min(Kth unit max, (K+1)th unit max + increment((K+1)th)), at least opening.
        - winners_map is {bidder_id: seats_allocated} among top K units.
        """
        from .models import ProxyBid  # local import
        proxies = list(
            ProxyBid.objects.filter(item=locked_item).select_for_update().order_by("-max_amount", "updated_at")
        )
        opening = Decimal(locked_item.opening_min_bid or Decimal("1.00"))
        K = int(locked_item.quantity_total or 1)
        K = max(1, K)
        units = []  # list of tuples (max_amount:Decimal, updated_at, bidder_id)
        for p in proxies:
            seats = max(1, int(getattr(p, "seats", 1) or 1))
            amt = Decimal(p.max_amount)
            for _ in range(seats):
                units.append((amt, p.updated_at, p.bidder_id))
        if not units:
            return None, opening, False, {}
        # Sort by amount desc, time asc
        units.sort(key=lambda t: (t[0] * -1, t[1]))
        if len(units) <= K:
            winners_map = {}
            for _, __, bidder_id in units[:]:
                winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
            # top bidder is the bidder_id of the highest unit
            top_bidder = units[0][2]
            return top_bidder, opening, False, winners_map
        # More than K units
        kth_max = Decimal(units[K - 1][0])
        next_max = Decimal(units[K][0])
        inc = Decimal(get_increment(next_max))
        price = min(kth_max, next_max + inc)
        price = max(price, opening)
        winners_map = {}
        for i in range(K):
            _, __, bidder_id = units[i]
            winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
        # leader = bidder with the top unit
        top_bidder = units[0][2]
        return top_bidder, price, True, winners_map

    try:
        with transaction.atomic():
            locked_item = Item.objects.select_for_update().get(pk=item.pk)

            from .models import ProxyBid, Bid  # local import to avoid circulars

            # Current state before change
            prev_top = locked_item.bids.order_by("-amount", "-created_at").first()
            prev_leader, prev_price, prev_full, prev_winners = compute_current_state(locked_item)

            # Upsert user's proxy bid
            pb, created = ProxyBid.objects.select_for_update().get_or_create(
                item=locked_item, bidder=request.user, defaults={"max_amount": max_amount, "seats": req_seats}
            )
            changed = False
            if not created and max_amount > pb.max_amount:
                pb.max_amount = max_amount
                changed = True
            # update requested seats if changed
            if getattr(pb, "seats", 1) != req_seats:
                pb.seats = req_seats
                changed = True
            if changed:
                pb.save(update_fields=["max_amount", "seats", "updated_at"]) if hasattr(pb, "seats") else pb.save(update_fields=["max_amount", "updated_at"])

            # Recompute after change
            new_leader, new_price, new_full, new_winners = compute_current_state(locked_item)

            # Validation:
            # - If not full before, require at least opening minimum
            # - If full before and user is not among new winners, guidance: need at least prev_price + increment(prev_price)
            if not prev_full:
                opening_req = Decimal(locked_item.opening_min_bid or Decimal("1.00"))
                if max_amount < opening_req:
                    messages.error(request, f"Your maximum must be at least {opening_req}.")
                    return redirect("auctions:item_detail", slug=locked_item.slug)
            else:
                if request.user.id not in new_winners:
                    min_next = prev_price + Decimal(get_increment(prev_price))
                    if max_amount < min_next and (not created and max_amount <= pb.max_amount):
                        messages.error(request, f"Your maximum must be at least {min_next} to secure a spot.")
                        return redirect("auctions:item_detail", slug=locked_item.slug)

            # If the public price/leader changed, record a Bid row for audit/visibility
            should_write_bid = (
                (prev_top is None) or (Decimal(prev_top.amount) != new_price) or (prev_leader != new_leader)
            )
            if should_write_bid and new_leader is not None:
                # new_leader is a bidder_id from compute_current_state
                Bid.objects.create(item=locked_item, bidder_id=new_leader, amount=new_price)

    except Exception:
        messages.error(request, "Unable to place bid right now. Please try again.")
        return redirect("auctions:item_detail", slug=item.slug)

    # Messaging
    # Messaging considers seat allocation rather than only top leader
    prev_won = 0
    new_won = 0
    try:
        prev_won = prev_winners.get(request.user.id, 0)
        new_won = new_winners.get(request.user.id, 0)
    except Exception:
        prev_won = 0
        new_won = 0
    if new_won > 0:
        if prev_won > 0:
            messages.success(request, f"Your maximum was updated. You're still winning {new_won} seat(s).")
        else:
            messages.success(request, f"You're now winning {new_won} seat(s).")
    else:
        messages.info(request, "Your maximum was recorded, but you're not winning a seat yet.")

    return redirect("auctions:item_detail", slug=item.slug)

@manager_required
def manager_home(request):
    return render(request, "auctions/manager_home.html", {})


@manager_required
def manager_approvals(request):
    """List draft items awaiting approval/publish by managers.

    Shows items in draft state with quick actions to publish.
    """
    items = (
        Item.objects.select_related("auction", "category", "donor")
        .filter(status=Item.STATUS_DRAFT)
        .order_by("-created_at")
    )
    return render(request, "auctions/manager_approvals.html", {"items": items})


@manager_required
def manager_update_item(request, slug):
    """Handle inline manager edits for an item from approvals page."""
    if request.method != "POST":
        return redirect("auctions:manager_approvals")
    item = get_object_or_404(Item, slug=slug)
    form = ManagerItemApprovalForm(request.POST, instance=item)
    if form.is_valid():
        form.save()
        messages.success(request, "Item updated.")
    else:
        messages.error(request, "Please correct the errors in the item.")
    return redirect("auctions:manager_approvals")


@login_required
def fixed_price_adjust(request, slug):
    if request.method != "POST":
        return redirect("auctions:item_detail", slug=slug)
    try:
        with transaction.atomic():
            item = Item.objects.select_for_update().get(slug=slug)
            signup = Signup.objects.filter(item=item, user=request.user).first()
            if not signup:
                messages.error(request, "You don't have a signup to adjust.")
                # HTMX: re-render signup section
                if request.headers.get("HX-Request") == "true":
                    # recompute context
                    can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
                    user_signup = None
                    spots_left = max(0, (item.quantity_total or 0) - (item.quantity_sold or 0))
                    ctx = {
                        "item": item,
                        "can_signup": can_signup,
                        "user_signup": user_signup,
                        "spots_left": spots_left,
                    }
                    return render(request, "auctions/partials/signup_section.html", ctx)
                return redirect("auctions:item_detail", slug=item.slug)
            try:
                new_qty = int((request.POST.get("quantity") or "").strip() or "0")
            except Exception:
                new_qty = 0
            new_qty = max(1, new_qty)
            old_qty = signup.quantity or 1
            if new_qty == old_qty:
                messages.info(request, "No changes to your seats.")
                if request.headers.get("HX-Request") == "true":
                    # render current state
                    can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
                    spots_left = max(0, (item.quantity_total or 0) - (item.quantity_sold or 0))
                    ctx = {"item": item, "can_signup": can_signup, "user_signup": signup, "spots_left": spots_left}
                    return render(request, "auctions/partials/signup_section.html", ctx)
                return redirect("auctions:item_detail", slug=item.slug)

            # If currently waitlisted, just update quantity; promotion handled elsewhere
            if signup.waitlisted:
                signup.quantity = new_qty
                signup.save(update_fields=["quantity"])
                messages.success(request, "Waitlist quantity updated.")
                if request.headers.get("HX-Request") == "true":
                    can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
                    spots_left = max(0, (item.quantity_total or 0) - (item.quantity_sold or 0))
                    ctx = {"item": item, "can_signup": can_signup, "user_signup": signup, "spots_left": spots_left}
                    return render(request, "auctions/partials/signup_section.html", ctx)
                return redirect("auctions:item_detail", slug=item.slug)

            # Confirmed signup adjustments
            capacity = item.quantity_total or 0
            # Current confirmed total (including this signup)
            current_confirmed = (
                Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
                or 0
            )

            if new_qty > old_qty:
                delta = new_qty - old_qty
                remaining = max(0, capacity - current_confirmed)
                if remaining < delta:
                    messages.error(
                        request,
                        f"Only {remaining} more seat(s) available. Reduce quantity or try later.",
                    )
                    if request.headers.get("HX-Request") == "true":
                        can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
                        # no state change yet
                        spots_left = max(0, (item.quantity_total or 0) - (item.quantity_sold or 0))
                        ctx = {"item": item, "can_signup": can_signup, "user_signup": signup, "spots_left": spots_left}
                        return render(request, "auctions/partials/signup_section.html", ctx)
                    return redirect("auctions:item_detail", slug=item.slug)
                # apply increase
                signup.quantity = new_qty
                signup.save(update_fields=["quantity"])
                item.quantity_sold = current_confirmed + delta
                item.save(update_fields=["quantity_sold"])
                messages.success(request, "Seats increased.")
                if request.headers.get("HX-Request") == "true":
                    can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
                    spots_left = max(0, (item.quantity_total or 0) - (item.quantity_sold or 0))
                    ctx = {"item": item, "can_signup": can_signup, "user_signup": signup, "spots_left": spots_left}
                    return render(request, "auctions/partials/signup_section.html", ctx)
                return redirect("auctions:item_detail", slug=item.slug)
            else:
                # decreasing quantity
                delta = old_qty - new_qty
                signup.quantity = new_qty
                signup.save(update_fields=["quantity"])
                # recompute confirmed then try to promote waitlist FIFO
                current_confirmed = (
                    Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
                    or 0
                )
                item.quantity_sold = max(0, current_confirmed)
                remaining = max(0, capacity - item.quantity_sold)
                if remaining > 0:
                    waitlisted = list(
                        Signup.objects.filter(item=item, waitlisted=True)
                        .order_by("created_at")
                        .select_for_update()
                    )
                    promoted_any = False
                    for w in waitlisted:
                        if w.quantity <= remaining:
                            w.waitlisted = False
                            w.save(update_fields=["waitlisted"])
                            item.quantity_sold += w.quantity
                            remaining -= w.quantity
                            promoted_any = True
                        if remaining <= 0:
                            break
                    if promoted_any:
                        messages.info(request, "Waitlisted attendee(s) were promoted.")
                item.save(update_fields=["quantity_sold"])
                messages.success(request, "Seats decreased.")
                if request.headers.get("HX-Request") == "true":
                    can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
                    spots_left = max(0, (item.quantity_total or 0) - (item.quantity_sold or 0))
                    ctx = {"item": item, "can_signup": can_signup, "user_signup": signup, "spots_left": spots_left}
                    return render(request, "auctions/partials/signup_section.html", ctx)
                return redirect("auctions:item_detail", slug=item.slug)
    except Exception:
        messages.error(request, "Unable to adjust seats right now. Please try again later.")
        if request.headers.get("HX-Request") == "true":
            # best-effort partial render
            item = get_object_or_404(Item, slug=slug)
            can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
            signup = Signup.objects.filter(item=item, user=request.user).first()
            spots_left = max(0, (item.quantity_total or 0) - (item.quantity_sold or 0))
            ctx = {"item": item, "can_signup": can_signup, "user_signup": signup, "spots_left": spots_left}
            return render(request, "auctions/partials/signup_section.html", ctx)
        return redirect("auctions:item_detail", slug=slug)


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            # Save the user, then force-login via our EmailBackend
            user = form.save()
            login(request, user, backend="auctions.auth_backends.EmailBackend")
            try:
                request.session.save()
            except Exception:
                pass
            messages.success(request, "Welcome! Your account has been created.")
            # Ensure a profile exists, then redirect to complete it
            Profile.objects.get_or_create(user=user)
            # Add user to Donor group if present
            try:
                donor_group = Group.objects.get(name="Donor")
                donor_group.user_set.add(user)
            except Group.DoesNotExist:
                pass
            return redirect("auctions:profile_complete")
    else:
        form = RegisterForm()
    return render(request, "auctions/register.html", {"form": form})


@login_required
def profile_complete(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("auctions:account_home")
    else:
        form = ProfileForm(instance=profile)
    return render(request, "auctions/profile_form.html", {"form": form, "profile": profile})


def login_view(request):
    if request.method == "POST":
        form = EmailLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            password = form.cleaned_data["password"]
            # Try email-based auth first
            user = authenticate(request, email=email, password=password)
            # Fall back to username-based auth for legacy users where username==email
            if user is None:
                user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                return redirect("auctions:catalog_list")
            messages.error(request, "Invalid credentials.")
    else:
        form = EmailLoginForm()
    return render(request, "auctions/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("auctions:catalog_list")


@login_required
def account_home(request):
    return render(request, "auctions/account_home.html", {})


@login_required
def account_tab_offered(request):
    """Items offered/donated by the current user."""
    items = (
        Item.objects.select_related("auction", "category")
        .filter(donor=request.user)
        .order_by("-created_at")
    )
    return render(request, "auctions/partials/account_tab_offered.html", {"items": items})


@login_required
def account_tab_winning(request):
    """Items where the user is currently winning one or more seats."""
    from .models import ProxyBid, Bid  # local import

    def get_increment(base: Decimal, item: Item) -> Decimal:
        return item.bid_increment if item.bid_increment is not None else standard_increment(base)

    def compute_current_state(locked_item: Item):
        proxies = list(
            ProxyBid.objects.filter(item=locked_item).order_by("-max_amount", "updated_at")
        )
        opening = Decimal(locked_item.opening_min_bid or Decimal("1.00"))
        K = max(1, int(locked_item.quantity_total or 1))
        units = []  # (amount, updated_at, bidder_id)
        for p in proxies:
            seats = max(1, int(getattr(p, "seats", 1) or 1))
            amt = Decimal(p.max_amount)
            for _ in range(seats):
                units.append((amt, p.updated_at, p.bidder_id))
        if not units:
            return None, opening, False, {}
        units.sort(key=lambda t: (t[0] * -1, t[1]))
        if len(units) <= K:
            winners_map = {}
            for _, __, bidder_id in units:
                winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
            top_bidder = units[0][2]
            return top_bidder, opening, False, winners_map
        kth_max = Decimal(units[K - 1][0])
        next_max = Decimal(units[K][0])
        inc = Decimal(get_increment(next_max, locked_item))
        price = min(kth_max, next_max + inc)
        price = max(price, opening)
        winners_map = {}
        for i in range(K):
            _, __, bidder_id = units[i]
            winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
        top_bidder = units[0][2]
        return top_bidder, price, True, winners_map

    # Candidate items: where user has a proxy or has bid on; exclude fixed-price
    items_qs = (
        Item.objects.select_related("auction", "category")
        .exclude(type=Item.TYPE_FIXED_PRICE)
        .filter(
            Q(proxy_bids__bidder=request.user) | Q(bids__bidder=request.user)
        )
        .order_by("title")
        .distinct()
    )
    items = []
    # Annotate each item with my_won_seats, current_price, my_max
    for it in items_qs:
        _, public_price, _, winners_map = compute_current_state(it)
        my_won = winners_map.get(request.user.id, 0)
        if my_won > 0:
            it.my_won_seats = my_won
            it.current_price = public_price
            it.my_max = (
                ProxyBid.objects.filter(item=it, bidder=request.user).values_list("max_amount", flat=True).first()
            )
            items.append(it)
    return render(request, "auctions/partials/account_tab_winning.html", {"items": items})


@login_required
def account_tab_outbid(request):
    """Items the user has bid on but is currently winning 0 seats."""
    from .models import ProxyBid, Bid  # local import

    def get_increment(base: Decimal, item: Item) -> Decimal:
        return item.bid_increment if item.bid_increment is not None else standard_increment(base)

    def compute_current_state(locked_item: Item):
        proxies = list(
            ProxyBid.objects.filter(item=locked_item).order_by("-max_amount", "updated_at")
        )
        opening = Decimal(locked_item.opening_min_bid or Decimal("1.00"))
        K = max(1, int(locked_item.quantity_total or 1))
        units = []
        for p in proxies:
            seats = max(1, int(getattr(p, "seats", 1) or 1))
            amt = Decimal(p.max_amount)
            for _ in range(seats):
                units.append((amt, p.updated_at, p.bidder_id))
        if not units:
            return None, opening, False, {}
        units.sort(key=lambda t: (t[0] * -1, t[1]))
        if len(units) <= K:
            winners_map = {}
            for _, __, bidder_id in units:
                winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
            top_bidder = units[0][2]
            return top_bidder, opening, False, winners_map
        kth_max = Decimal(units[K - 1][0])
        next_max = Decimal(units[K][0])
        inc = Decimal(get_increment(next_max, locked_item))
        price = min(kth_max, next_max + inc)
        price = max(price, opening)
        winners_map = {}
        for i in range(K):
            _, __, bidder_id = units[i]
            winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
        top_bidder = units[0][2]
        return top_bidder, price, True, winners_map

    items_qs = (
        Item.objects.select_related("auction", "category")
        .exclude(type=Item.TYPE_FIXED_PRICE)
        .filter(
            Q(proxy_bids__bidder=request.user) | Q(bids__bidder=request.user)
        )
        .order_by("title")
        .distinct()
    )
    items = []
    for it in items_qs:
        _, public_price, _, winners_map = compute_current_state(it)
        my_won = winners_map.get(request.user.id, 0)
        if my_won == 0:
            it.current_price = public_price
            it.my_max = (
                ProxyBid.objects.filter(item=it, bidder=request.user).values_list("max_amount", flat=True).first()
            )
            items.append(it)
    return render(request, "auctions/partials/account_tab_outbid.html", {"items": items})


@login_required
def account_update_proxy_max(request, slug):
    """Allow a user to increase their proxy max for an item from the account page.

    Accepts POST with 'amount'. On success, refreshes the winning or outbid tab via HTMX,
    or redirects back to account_home otherwise.
    """
    if request.method != "POST":
        return redirect("auctions:account_home")

    item = get_object_or_404(Item.objects.select_related("auction"), slug=slug)
    if item.status != Item.STATUS_PUBLISHED or item.type == Item.TYPE_FIXED_PRICE:
        messages.error(request, "Bidding is not allowed on this item.")
        return redirect("auctions:account_home")

    raw_amount = (request.POST.get("amount") or "").strip()
    try:
        new_max = Decimal(raw_amount)
    except Exception:
        messages.error(request, "Enter a valid amount.")
        return redirect("auctions:account_home")

    def get_increment(base: Decimal) -> Decimal:
        return item.bid_increment if item.bid_increment is not None else standard_increment(base)

    def compute_current_state(locked_item):
        from .models import ProxyBid  # local import
        proxies = list(
            ProxyBid.objects.filter(item=locked_item).select_for_update().order_by("-max_amount", "updated_at")
        )
        opening = Decimal(locked_item.opening_min_bid or Decimal("1.00"))
        K = int(locked_item.quantity_total or 1)
        K = max(1, K)
        units = []
        for p in proxies:
            seats = max(1, int(getattr(p, "seats", 1) or 1))
            amt = Decimal(p.max_amount)
            for _ in range(seats):
                units.append((amt, p.updated_at, p.bidder_id))
        if not units:
            return None, opening, False, {}
        units.sort(key=lambda t: (t[0] * -1, t[1]))
        if len(units) <= K:
            winners_map = {}
            for _, __, bidder_id in units[:]:
                winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
            top_bidder = proxies[0].bidder if proxies else None
            return top_bidder, opening, False, winners_map
        kth_max = Decimal(units[K - 1][0])
        next_max = Decimal(units[K][0])
        inc = Decimal(get_increment(next_max))
        price = min(kth_max, next_max + inc)
        price = max(price, opening)
        winners_map = {}
        for i in range(K):
            _, __, bidder_id = units[i]
            winners_map[bidder_id] = winners_map.get(bidder_id, 0) + 1
        top_bidder = units[0][2]
        return top_bidder, price, True, winners_map

    try:
        with transaction.atomic():
            locked_item = Item.objects.select_for_update().get(pk=item.pk)
            from .models import ProxyBid, Bid  # local import

            prev_top = locked_item.bids.order_by("-amount", "-created_at").first()
            prev_leader, prev_price, prev_full, prev_winners = compute_current_state(locked_item)

            # opening minimum validation when not full previously
            if not prev_full:
                opening_req = Decimal(locked_item.opening_min_bid or Decimal("1.00"))
                if new_max < opening_req:
                    messages.error(request, f"Your maximum must be at least {opening_req}.")
                    return redirect("auctions:account_home")

            pb, created = ProxyBid.objects.select_for_update().get_or_create(
                item=locked_item, bidder=request.user, defaults={"max_amount": new_max}
            )
            if not created and new_max > pb.max_amount:
                pb.max_amount = new_max
                pb.save(update_fields=["max_amount", "updated_at"])

            new_leader, new_price, new_full, new_winners = compute_current_state(locked_item)

            if prev_full and (new_winners.get(request.user.id, 0) == 0):
                min_next = prev_price + Decimal(get_increment(prev_price))
                if new_max < min_next and (not created and new_max <= pb.max_amount):
                    messages.error(request, f"Your maximum must be at least {min_next} to secure a spot.")
                    return redirect("auctions:account_home")

            should_write_bid = (
                (prev_top is None) or (Decimal(prev_top.amount) != new_price) or (prev_leader != new_leader)
            )
            if should_write_bid and new_leader is not None:
                # new_leader is a bidder_id from compute_current_state
                Bid.objects.create(item=locked_item, bidder_id=new_leader, amount=new_price)

    except Exception:
        messages.error(request, "Unable to update your maximum right now. Please try again.")
        if request.headers.get("HX-Request") == "true":
            # best-effort refresh
            return account_tab_winning(request)
        return redirect("auctions:account_home")

    # Seat-aware messaging
    try:
        prev_won = prev_winners.get(request.user.id, 0)
        new_won = new_winners.get(request.user.id, 0)
    except Exception:
        prev_won = 0
        new_won = 0
    if new_won > 0:
        if prev_won > 0:
            messages.success(request, f"Your maximum was updated. You're still winning {new_won} seat(s).")
        else:
            messages.success(request, f"You're now winning {new_won} seat(s).")
    else:
        messages.info(request, "Your maximum was recorded, but you're not winning a seat yet.")

    if request.headers.get("HX-Request") == "true":
        # Refresh appropriate tab based on current outcome
        if new_won > 0:
            return account_tab_winning(request)
        else:
            return account_tab_outbid(request)
    return redirect("auctions:account_home")


@login_required
def donor_item_create(request):
    if request.method == "POST":
        form = DonorItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            # assign latest auction and donor
            item.auction = Auction.objects.order_by("-year").first()
            item.donor = request.user
            item.status = Item.STATUS_DRAFT
            # generate a slug from title
            item.slug = unique_slug(Item, form.cleaned_data["title"])
            item.save()
            messages.success(request, "Draft item created.")
            return redirect("auctions:donor_item_edit", slug=item.slug)
    else:
        form = DonorItemForm()
    return render(request, "auctions/donor_item_form.html", {"form": form, "mode": "create"})


@login_required
def donor_item_edit(request, slug):
    item = get_object_or_404(Item, slug=slug)
    if item.donor_id != request.user.id:
        return redirect("auctions:account_home")
    if item.status != Item.STATUS_DRAFT:
        messages.error(request, "Only draft items can be edited by donors.")
        return redirect("auctions:account_home")
    if request.method == "POST":
        form = DonorItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "Draft item updated.")
            return redirect("auctions:donor_item_edit", slug=item.slug)
    else:
        form = DonorItemForm(instance=item)
    return render(request, "auctions/donor_item_form.html", {"form": form, "mode": "edit", "item": item})


@manager_required
def manager_publish_item(request, slug):
    item = get_object_or_404(Item, slug=slug)
    if item.status != Item.STATUS_DRAFT:
        messages.error(request, "Item is not in draft state.")
        return redirect("auctions:item_detail", slug=item.slug)
    item.status = Item.STATUS_PUBLISHED
    item.save(update_fields=["status"])
    messages.success(request, "Item published.")
    return redirect("auctions:item_detail", slug=item.slug)


@login_required
def fixed_price_signup(request, slug):
    if request.method != "POST":
        return redirect("auctions:item_detail", slug=slug)
    try:
        with transaction.atomic():
            item = (
                Item.objects.select_for_update().select_related("auction").get(slug=slug)
            )
            if item.type != Item.TYPE_FIXED_PRICE or item.status != Item.STATUS_PUBLISHED:
                messages.error(request, "Signups are not allowed for this item.")
                return redirect("auctions:item_detail", slug=item.slug)
            existing = Signup.objects.filter(item=item, user=request.user).first()
            if existing:
                messages.success(request, "You're signed up.")
                if request.headers.get("HX-Request") == "true":
                    capacity = item.quantity_total or 0
                    confirmed_sum = (
                        Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
                        or 0
                    )
                    item.quantity_sold = confirmed_sum
                    spots_left = max(0, capacity - confirmed_sum)
                    ctx = {"item": item, "can_signup": True, "user_signup": existing, "spots_left": spots_left}
                    return render(request, "auctions/partials/signup_section.html", ctx)
                return redirect("auctions:item_detail", slug=item.slug)
            # desired quantity (default 1)
            try:
                qty = int(request.POST.get("quantity", "1"))
            except Exception:
                qty = 1
            qty = max(1, qty)

            capacity = item.quantity_total or 0
            confirmed_sum = (
                Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
                or 0
            )
            remaining = max(0, capacity - confirmed_sum)

            if remaining >= qty:
                user_signup = Signup.objects.create(item=item, user=request.user, waitlisted=False, quantity=qty)
                item.quantity_sold = (confirmed_sum + qty)
                item.save(update_fields=["quantity_sold"])
                messages.success(request, "Signup confirmed.")
            else:
                # Not enough space; place entire request on waitlist
                user_signup = Signup.objects.create(item=item, user=request.user, waitlisted=True, quantity=qty)
                messages.info(request, "Waitlisted. You'll be promoted if a spot opens.")
            if request.headers.get("HX-Request") == "true":
                capacity = item.quantity_total or 0
                confirmed_sum = (
                    Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
                    or 0
                )
                item.quantity_sold = confirmed_sum
                spots_left = max(0, capacity - confirmed_sum)
                ctx = {"item": item, "can_signup": True, "user_signup": user_signup, "spots_left": spots_left}
                return render(request, "auctions/partials/signup_section.html", ctx)
    except Exception:
        messages.error(request, "Signup temporarily unavailable. Please try again later.")
    if request.headers.get("HX-Request") == "true":
        item = get_object_or_404(Item, slug=slug)
        can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
        user_signup = Signup.objects.filter(item=item, user=request.user).first()
        capacity = item.quantity_total or 0
        confirmed_sum = (
            Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
            or 0
        )
        item.quantity_sold = confirmed_sum
        spots_left = max(0, capacity - confirmed_sum)
        ctx = {"item": item, "can_signup": can_signup, "user_signup": user_signup, "spots_left": spots_left}
        return render(request, "auctions/partials/signup_section.html", ctx)
    return redirect("auctions:item_detail", slug=slug)


@csrf_exempt
@manager_required
def send_test_sms(request):
    """Send a test SMS via Telnyx to verify credentials.

    POST body params:
      - to: E.164 destination number (e.g., +15551234567)
      - text (optional): message text (default: 'Test from auction app')
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    import os
    to = (request.POST.get("to") or "").strip()
    if not to:
        return JsonResponse({"error": "Missing 'to' parameter"}, status=400)
    text = (request.POST.get("text") or "Test from auction app").strip()
    api_key = os.environ.get("TELNYX_API_KEY")
    profile_id = os.environ.get("TELNYX_MESSAGING_PROFILE_ID")
    from_number = os.environ.get("TELNYX_FROM_NUMBER")
    if not api_key:
        return JsonResponse({"error": "TELNYX_API_KEY not configured"}, status=500)
    if not (profile_id or from_number):
        return JsonResponse({"error": "TELNYX_MESSAGING_PROFILE_ID or TELNYX_FROM_NUMBER must be set"}, status=500)
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
        return JsonResponse({"ok": True, "message_id": getattr(msg, "id", None)}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def fixed_price_cancel(request, slug):
    if request.method != "POST":
        return redirect("auctions:item_detail", slug=slug)
    try:
        with transaction.atomic():
            item = Item.objects.select_for_update().get(slug=slug)
            signup = Signup.objects.filter(item=item, user=request.user).first()
            if not signup:
                if request.headers.get("HX-Request") == "true":
                    can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
                    user_signup = None
                    capacity = item.quantity_total or 0
                    confirmed_sum = (
                        Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
                        or 0
                    )
                    item.quantity_sold = confirmed_sum
                    spots_left = max(0, capacity - confirmed_sum)
                    ctx = {"item": item, "can_signup": can_signup, "user_signup": user_signup, "spots_left": spots_left}
                    return render(request, "auctions/partials/signup_section.html", ctx)
                return redirect("auctions:item_detail", slug=item.slug)
            was_waitlisted = signup.waitlisted
            freed_qty = signup.quantity or 1
            signup.delete()
            if not was_waitlisted:
                # free slots, decrement sold then try to promote waitlist FIFO if capacity allows
                current_confirmed = (
                    Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
                    or 0
                )
                item.quantity_sold = max(0, current_confirmed)
                capacity = item.quantity_total or 0
                remaining = max(0, capacity - item.quantity_sold)
                if remaining > 0:
                    # Promote as many waitlisted signups as possible fully (no partial promotion)
                    waitlisted = list(
                        Signup.objects.filter(item=item, waitlisted=True).order_by("created_at").select_for_update()
                    )
                    promoted_any = False
                    for w in waitlisted:
                        if w.quantity <= remaining:
                            w.waitlisted = False
                            w.save(update_fields=["waitlisted"])
                            item.quantity_sold += w.quantity
                            remaining -= w.quantity
                            promoted_any = True
                        if remaining <= 0:
                            break
                    if promoted_any:
                        messages.info(request, "Waitlisted attendee(s) were promoted.")
                item.save(update_fields=["quantity_sold"])
        messages.success(request, "Your signup was canceled.")
    except Exception:
        messages.error(request, "Unable to cancel at this time. Please try again later.")
    if request.headers.get("HX-Request") == "true":
        item = get_object_or_404(Item, slug=slug)
        can_signup = item.status == Item.STATUS_PUBLISHED and item.type == Item.TYPE_FIXED_PRICE
        user_signup = Signup.objects.filter(item=item, user=request.user).first()
        capacity = item.quantity_total or 0
        confirmed_sum = (
            Signup.objects.filter(item=item, waitlisted=False).aggregate(s=Sum("quantity")).get("s")
            or 0
        )
        item.quantity_sold = confirmed_sum
        spots_left = max(0, capacity - confirmed_sum)
        ctx = {"item": item, "can_signup": can_signup, "user_signup": user_signup, "spots_left": spots_left}
        return render(request, "auctions/partials/signup_section.html", ctx)
    return redirect("auctions:item_detail", slug=slug)
