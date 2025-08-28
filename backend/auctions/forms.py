from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from decimal import Decimal
from .models import Item, Profile
from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Checkbox

User = get_user_model()


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Placeholders and autofocus for nicer UX
        self.fields["email"].widget = forms.EmailInput(
            attrs={"placeholder": "you@example.com", "autofocus": True}
        )
        self.fields["first_name"].widget = forms.TextInput(
            attrs={"placeholder": "Ada"}
        )
        self.fields["last_name"].widget = forms.TextInput(
            attrs={"placeholder": "Lovelace"}
        )
        self.fields["password"].widget = forms.PasswordInput(
            attrs={"placeholder": "At least 8 characters"}
        )
        self.fields["password_confirm"].widget = forms.PasswordInput(
            attrs={"placeholder": "Re-enter password"}
        )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned


class ManagerItemApprovalForm(forms.ModelForm):
    """Lightweight form for managers/admins to tweak core text fields before publishing."""

    class Meta:
        model = Item
        fields = [
            "title",
            "description",
            "restrictions",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Title"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "textarea", "placeholder": "Description"}),
            "restrictions": forms.Textarea(attrs={"rows": 2, "class": "textarea", "placeholder": "Restrictions"}),
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "image",
            "phone",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
        ]
        widgets = {
            "image": forms.FileInput(attrs={"accept": "image/*"}),
            "address_line1": forms.TextInput(attrs={"placeholder": "123 Main St"}),
            "address_line2": forms.TextInput(attrs={"placeholder": "Apt/Suite"}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "state": forms.TextInput(attrs={"placeholder": "State"}),
            "postal_code": forms.TextInput(attrs={"placeholder": "ZIP/Postal Code"}),
            "country": forms.TextInput(attrs={"placeholder": "Country"}),
        }


class EmailLoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget = forms.EmailInput(
            attrs={"placeholder": "you@example.com", "autofocus": True}
        )
        self.fields["password"].widget = forms.PasswordInput(
            attrs={"placeholder": "Your password"}
        )


class DonorItemForm(forms.ModelForm):
    enable_buy_now = forms.BooleanField(
        required=False,
        label="Offer Buy-It-Now option",
        help_text="If checked, set a Buy-It-Now price (defaults to the opening minimum bid).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Donor form should NOT offer "Fixed Price Signup"; those are created in phase 2 by managers.
        try:
            self.fields["type"].choices = [
                (val, label)
                for (val, label) in Item.TYPE_CHOICES
                if val != Item.TYPE_FIXED_PRICE
            ]
        except Exception:
            pass

        # Use browser-friendly datetime-local widgets for event times
        for f in ("event_starts_at", "event_ends_at"):
            if f in self.fields:
                self.fields[f].widget = forms.DateTimeInput(
                    attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
                )
                # Accept HTML5 datetime-local value format
                try:
                    self.fields[f].input_formats = ["%Y-%m-%dT%H:%M"]
                except Exception:
                    pass
                # If initial value exists, ensure it renders in the widget's format
                val = self.initial.get(f) or getattr(self.instance, f, None)
                if val is not None and not self.is_bound:
                    try:
                        self.initial[f] = val.strftime("%Y-%m-%dT%H:%M")
                    except Exception:
                        pass

        # Place buy-now controls next to bidding fields; default price to opening minimum
        opening = None
        if self.instance and getattr(self.instance, "opening_min_bid", None):
            opening = self.instance.opening_min_bid
        elif self.data.get("opening_min_bid"):
            try:
                opening = Decimal(self.data.get("opening_min_bid"))
            except Exception:
                opening = None

        # Initial state: enable if model has a buy_now_price; otherwise default enabled
        has_price = bool(getattr(self.instance, "buy_now_price", None))
        if not self.is_bound:
            self.fields["enable_buy_now"].initial = True if opening is None else True
            if has_price:
                self.fields["enable_buy_now"].initial = True
                self.fields["buy_now_price"].initial = self.instance.buy_now_price
            elif opening is not None:
                self.fields["buy_now_price"].initial = opening

    class Meta:
        model = Item
        fields = [
            "title",
            "type",
            "category",
            "description",
            "restrictions",
            "image",
            # Event details
            "event_starts_at",
            "event_ends_at",
            "at_church",
            "location_name",
            "location_address",
            "opening_min_bid",
            "buy_now_price",
            # Fixed price and quantity are manager-phase; keep quantity for capacity of events
            "quantity_total",
        ]
        widgets = {
            "location_address": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "restrictions": forms.Textarea(attrs={"rows": 3}),
            "image": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def clean(self):
        cleaned = super().clean()
        t = cleaned.get("type")
        opening = cleaned.get("opening_min_bid")
        qty = cleaned.get("quantity_total")
        at_church = cleaned.get("at_church")
        loc_name = (cleaned.get("location_name") or "").strip()
        loc_addr = (cleaned.get("location_address") or "").strip()
        enable_buy = cleaned.get("enable_buy_now")
        buy_now = cleaned.get("buy_now_price")

        # Donors cannot create fixed-price items at this stage
        if t == Item.TYPE_FIXED_PRICE:
            self.add_error("type", "Fixed price signups are created during phase 2 by managers.")
            # Also surface as a non-field error for visibility in templates
            self.add_error(None, "Fixed price signups are created during phase 2 by managers.")

        # bidding types need opening minimum; increment will be automatic
        if t in (Item.TYPE_GOOD, Item.TYPE_SERVICE, Item.TYPE_EVENT):
            if opening in (None, ""):
                self.add_error("opening_min_bid", "Required for bidding items.")

            # Buy-It-Now handling
            if not enable_buy:
                cleaned["buy_now_price"] = None
            else:
                # Default to opening min if not provided
                if buy_now in (None, "") and opening not in (None, ""):
                    cleaned["buy_now_price"] = opening
                # Validate price is >= opening minimum
                if cleaned.get("buy_now_price") is not None and opening not in (None, ""):
                    try:
                        if Decimal(cleaned["buy_now_price"]) < Decimal(opening):
                            self.add_error("buy_now_price", "Must be at least the opening minimum bid.")
                    except Exception:
                        pass

        # Events: location can be provided later by managers/hosts; don't block donor creation
        # (Managers can enforce completeness before publishing.)

        # If both times provided, ensure logical ordering
        starts = cleaned.get("event_starts_at")
        ends = cleaned.get("event_ends_at")
        if starts and ends and ends <= starts:
            self.add_error("event_ends_at", "End must be after start.")

        # basic positivity checks
        for field in ("opening_min_bid", "buy_now_price"):
            val = cleaned.get(field)
            if val is not None and val <= Decimal(0):
                self.add_error(field, "Must be positive.")
        if qty is not None and qty < 1:
            self.add_error("quantity_total", "Must be at least 1.")
        return cleaned
