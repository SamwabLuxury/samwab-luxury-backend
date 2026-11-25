import pytest
from django.test import Client

from apps.shop.listings.tests.helpers import make_admin
from apps.users.accounts.tests.helpers import admin_login


@pytest.fixture
def admin_client_two_step(client: Client) -> Client:
    admin_login(client, make_admin())
    return client
