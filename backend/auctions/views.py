from django.shortcuts import get_object_or_404, render
from django.db.models import Prefetch, Sum
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
    categories = Category.objects.filter(active=True).order_by("sort_order", "name")
    items = (
        Item.objects.select_related("auction", "category")
        .filter(status=Item.STATUS_PUBLISHED)
        .order_by("title")
    )
    # Prefetch items per category for simple grouped display
    categories = categories.prefetch_related(
        Prefetch(
            "items",
            queryset=items,
            to_attr="published_items",
        )
    )
    return render(request, "auctions/catalog_list.html", {"categories": categories})


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
    if can_bid:
        try:
            top_bid = item.bids.order_by("-amount", "-created_at").first()
        except Exception:
            top_bid = None
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

    # Parse amount
    raw_amount = (request.POST.get("amount") or "").strip()
    try:
        amount = Decimal(raw_amount)
    except Exception:
        messages.error(request, "Enter a valid bid amount.")
        return redirect("auctions:item_detail", slug=item.slug)

    # Determine minimum required bid
    try:
        top_bid = item.bids.order_by("-amount", "-created_at").first()
    except Exception:
        top_bid = None

    min_required = None
    if top_bid:
        # Use explicit increment if provided, else a sensible standard increment
        incr = item.bid_increment if item.bid_increment is not None else standard_increment(top_bid.amount)
        min_required = (top_bid.amount or Decimal("0")) + Decimal(incr)
    else:
        # First bid must meet or exceed opening minimum if defined
        if item.opening_min_bid is not None:
            min_required = Decimal(item.opening_min_bid)
        else:
            min_required = Decimal("1.00")

    if amount < min_required:
        messages.error(request, f"Bid must be at least {min_required}.")
        return redirect("auctions:item_detail", slug=item.slug)

    # Optional idempotency key to prevent duplicate submissions
    idem = (request.POST.get("idempotency_key") or "").strip() or None

    # Create bid atomically and re-check top in case of race
    try:
        with transaction.atomic():
            # Lock row and recompute requirement in transaction
            locked_item = Item.objects.select_for_update().get(pk=item.pk)
            locked_top = locked_item.bids.order_by("-amount", "-created_at").first()
            if locked_top:
                incr2 = locked_item.bid_increment if locked_item.bid_increment is not None else standard_increment(locked_top.amount)
                min_req2 = (locked_top.amount or Decimal("0")) + Decimal(incr2)
            else:
                min_req2 = Decimal(locked_item.opening_min_bid or Decimal("1.00"))
            if amount < min_req2:
                messages.error(request, f"Another bid just came in. Minimum is now {min_req2}.")
                return redirect("auctions:item_detail", slug=locked_item.slug)

            from .models import Bid  # local import to avoid circulars at import time
            Bid.objects.create(item=locked_item, bidder=request.user, amount=amount, idempotency_key=idem)
    except IntegrityError:
        # Treat duplicate idempotent submission as success
        messages.info(request, "Duplicate submission ignored.")
    except Exception:
        messages.error(request, "Unable to place bid right now. Please try again.")
        return redirect("auctions:item_detail", slug=item.slug)

    messages.success(request, "Your bid has been placed.")
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
