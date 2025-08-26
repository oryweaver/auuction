import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_registration_creates_user_and_logs_in(client):
    url = reverse("auctions:register")
    resp = client.post(
        url,
        {
            "email": "test@example.org",
            "first_name": "Test",
            "last_name": "User",
            "password": "secret12345",
            "password_confirm": "secret12345",
        },
        follow=True,
    )
    assert resp.status_code == 200
    # user exists
    u = User.objects.get(email__iexact="test@example.org")
    assert u.first_name == "Test"
    # session shows logged in (account page accessible)
    resp2 = client.get(reverse("auctions:account_home"))
    assert resp2.status_code == 200


@pytest.mark.django_db
def test_login_with_email(client):
    u = User.objects.create_user(
        username="test@example.org", email="test@example.org", password="secret12345"
    )
    url = reverse("auctions:login")
    resp = client.post(url, {"email": "test@example.org", "password": "secret12345"}, follow=True)
    assert resp.status_code == 200
    # now account page accessible
    assert client.get(reverse("auctions:account_home")).status_code == 200


@pytest.mark.django_db
def test_account_requires_login(client):
    # not logged in -> redirect to login
    resp = client.get(reverse("auctions:account_home"))
    assert resp.status_code in (302, 301)
    assert reverse("auctions:login") in resp.headers.get("Location", "")
