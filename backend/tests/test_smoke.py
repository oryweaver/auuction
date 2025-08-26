import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health(client):
    resp = client.get("/health/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_catalog_home(client):
    resp = client.get("/")
    assert resp.status_code == 200
