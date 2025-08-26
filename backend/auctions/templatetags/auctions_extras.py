from django import template
from auctions.utils import is_manager as _is_manager
import hashlib

register = template.Library()


@register.filter(name="is_manager")
def is_manager(user):
    try:
        return _is_manager(user)
    except Exception:
        return False


@register.simple_tag
def avatar_url(user, size=32):
    """Return a Gravatar URL for the user email. Non-invasive; no DB changes required.
    size: pixel size, int.
    """
    try:
        email = (getattr(user, "email", "") or "").strip().lower()
        if not email:
            # default anonymous avatar
            return f"https://www.gravatar.com/avatar/?s={int(size)}&d=mp"
        h = hashlib.md5(email.encode("utf-8")).hexdigest()
        return f"https://www.gravatar.com/avatar/{h}?s={int(size)}&d=mp"
    except Exception:
        return f"https://www.gravatar.com/avatar/?s={int(size)}&d=mp"


@register.filter(name="initials")
def initials(user):
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    if first or last:
        return (first[:1] + last[:1]).upper()
    email = (getattr(user, "email", "") or "").strip()
    return (email[:1] or "?").upper()


@register.simple_tag
def user_avatar_url(user, size=48):
    """Prefer the uploaded profile image if present; otherwise use Gravatar.
    Safe to call even if Profile does not exist.
    """
    try:
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "image", None) and getattr(prof.image, "url", None):
            return prof.image.url
    except Exception:
        pass
    # fallback to gravatar
    return avatar_url(user, size)
