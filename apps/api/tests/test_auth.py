from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import login, promote_to_admin, register_user, set_active, unique_email

PASSWORD = "correct-horse-battery"


async def test_register_creates_client_user(client: AsyncClient) -> None:
    email = unique_email()
    user = await register_user(client, email=email)
    assert user["email"] == email
    assert user["role"] == "client"
    assert user["is_active"] is True
    assert "hashed_password" not in user


async def test_register_normalizes_email_case(client: AsyncClient) -> None:
    email = unique_email()
    user = await register_user(client, email=email.upper())
    assert user["email"] == email


async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Dup"},
    )
    assert response.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "short", "full_name": "Weak"},
    )
    assert response.status_code == 422


async def test_login_returns_token_pair(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    tokens = await login(client, email=email, password=PASSWORD)
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] != tokens["refresh_token"]
    assert int(tokens["expires_in"]) > 0


async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password-123"}
    )
    assert response.status_code == 401


async def test_login_unknown_user_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email(), "password": PASSWORD}
    )
    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_me_returns_current_user(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    tokens = await login(client, email=email, password=PASSWORD)
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == email


async def test_refresh_rotates_tokens(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    tokens = await login(client, email=email, password=PASSWORD)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed["refresh_token"] != tokens["refresh_token"]

    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {refreshed['access_token']}"}
    )
    assert me.status_code == 200


async def test_access_token_rejected_as_refresh_token(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    tokens = await login(client, email=email, password=PASSWORD)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401


async def test_refresh_token_rejected_as_access_token(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    tokens = await login(client, email=email, password=PASSWORD)
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401


async def test_garbage_token_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


async def test_inactive_user_cannot_login(client: AsyncClient, app: FastAPI) -> None:
    email = unique_email("inactive")
    await register_user(client, email=email)
    await set_active(app, email, is_active=False)

    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 401


async def test_deactivation_revokes_existing_access_token(
    client: AsyncClient, app: FastAPI
) -> None:
    email = unique_email("revoked")
    await register_user(client, email=email)
    tokens = await login(client, email=email, password=PASSWORD)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 200

    await set_active(app, email, is_active=False)
    # get_current_user re-checks is_active on every request, so the still-valid
    # JWT no longer grants access.
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401


async def test_rbac_client_cannot_list_users(client: AsyncClient) -> None:
    email = unique_email()
    await register_user(client, email=email)
    tokens = await login(client, email=email, password=PASSWORD)
    response = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 403


async def test_rbac_admin_can_list_users(client: AsyncClient, app: FastAPI) -> None:
    admin_email = unique_email("admin")
    await register_user(client, email=admin_email)
    await promote_to_admin(app, admin_email)
    # Re-login so the access token carries the admin role claim.
    tokens = await login(client, email=admin_email, password=PASSWORD)

    other_email = unique_email("member")
    await register_user(client, email=other_email)

    response = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    emails = {item["email"] for item in body["items"]}
    assert {admin_email, other_email} <= emails
