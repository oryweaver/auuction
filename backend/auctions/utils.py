from django.utils.text import slugify
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from decimal import Decimal


def unique_slug(model, base: str, slug_field: str = "slug") -> str:
    base_slug = slugify(base)[:50] or "item"
    slug = base_slug
    i = 2
    while model.objects.filter(**{slug_field: slug}).exists():
        slug = f"{base_slug}-{i}"
        i += 1
    return slug


def is_manager(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    try:
        return user.groups.filter(name="Manager").exists()
    except Group.DoesNotExist:
        return False


def manager_required(view_func):
    """Decorate a view to require manager privileges.

    - Requires authenticated user
    - Allows staff/superuser or member of 'Manager' group
    - Redirects to account_home with an error message if unauthorized
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if is_manager(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, "Managers only.")
        return redirect("auctions:account_home")

    return _wrapped


def standard_increment(current: Decimal) -> Decimal:
    """Return the standard bid increment based on the current value.

    Tiers (inclusive lower bounds):
      - < 25       -> 1
      - 25 - <100  -> 5
      - 100 - <250 -> 10
      - 250 - <500 -> 25
      - 500 - <1000-> 50
      - >= 1000    -> 100
    """
    if current is None:
        current = Decimal("0")
    # Ensure Decimal
    current = Decimal(current)
    if current < Decimal("25"):
        return Decimal("1")
    if current < Decimal("100"):
        return Decimal("5")
    if current < Decimal("250"):
        return Decimal("10")
    if current < Decimal("500"):
        return Decimal("25")
    if current < Decimal("1000"):
        return Decimal("50")
    return Decimal("100")
