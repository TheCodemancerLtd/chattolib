"""Integration tests against the live Chatto API.

Run with:  pytest tests/test_integration.py -v
Requires: CHATTO_LOGIN and CHATTO_PASSWORD environment variables.
"""

import os

import pytest

from chattolib.client import ChattoClient
from chattolib.exceptions import ChattoAuthError


pytestmark = pytest.mark.skipif(
    not os.environ.get("CHATTO_LOGIN") or not os.environ.get("CHATTO_PASSWORD"),
    reason="CHATTO_LOGIN and CHATTO_PASSWORD env vars required",
)


@pytest.fixture
async def client():
    c = await ChattoClient.login(
        os.environ["CHATTO_LOGIN"],
        os.environ["CHATTO_PASSWORD"],
    )
    async with c:
        yield c


async def test_login_and_me(client):
    user = await client.me()
    assert user.id
    assert user.login == os.environ["CHATTO_LOGIN"]
    print(f"Logged in as {user.login} (id={user.id})")


async def test_invalid_login():
    with pytest.raises(ChattoAuthError, match="Invalid credentials"):
        await ChattoClient.login("nonexistent_user_xyz", "wrongpassword")


async def test_list_spaces(client):
    spaces = await client.spaces()
    assert isinstance(spaces, list)
    print(f"Found {len(spaces)} spaces")
    for s in spaces:
        print(f"  - {s.name} (id={s.id}, members={s.member_count})")
