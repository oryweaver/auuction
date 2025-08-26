from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from decimal import Decimal
from .models import Item, Profile

User = get_user_model()


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure full model TYPE_CHOICES (including 'fixed') are present,
        # so we can return our friendly validation message instead of invalid-choice.
        try:
            self.fields["type"].choices = Item.TYPE_CHOICES
        except Exception:
            pass

    class Meta:
        model = Item
        fields = [
            "title",
            "type",
            "category",
            "description",
            "restrictions",
            "image",
            "at_church",
            "location_name",
            "location_address",
            "opening_min_bid",
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

        # Donors cannot create fixed-price items at this stage
        if t == Item.TYPE_FIXED_PRICE:
            self.add_error("type", "Required for fixed price items.")
            # Also surface as a non-field error for visibility in templates
            self.add_error(None, "Required for fixed price items.")

        # bidding types need opening minimum; increment will be automatic
        if t in (Item.TYPE_GOOD, Item.TYPE_SERVICE, Item.TYPE_EVENT):
            if opening in (None, ""):
                self.add_error("opening_min_bid", "Required for bidding items.")

        # Events: location can be provided later by managers/hosts; don't block donor creation
        # (Managers can enforce completeness before publishing.)

        # basic positivity checks
        for field in ("opening_min_bid",):
            val = cleaned.get(field)
            if val is not None and val <= Decimal(0):
                self.add_error(field, "Must be positive.")
        if qty is not None and qty < 1:
            self.add_error("quantity_total", "Must be at least 1.")
        return cleaned
