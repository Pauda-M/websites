from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.integrations.workspace.application.workspace import WorkspaceContext
from pb_api.integrations.workspace.domain.connection import WorkspaceConnection
from pb_api.integrations.workspace.security.crypto import CredentialCipher, generate_key


def test_cipher_round_trip_and_rejects_tampering() -> None:
    cipher = CredentialCipher.from_key_material(generate_key())
    token = cipher.encrypt("super-secret-refresh-token")
    assert token != "super-secret-refresh-token"
    assert cipher.decrypt(token) == "super-secret-refresh-token"
    # A token minted under a different key (or a corrupt token) cannot be read.
    other = CredentialCipher.from_key_material(generate_key())
    with pytest.raises(ValueError, match="could not be decrypted"):
        cipher.decrypt(other.encrypt("x"))
    with pytest.raises(ValueError, match="could not be decrypted"):
        cipher.decrypt("not a valid token")


def test_key_rotation_decrypts_old_and_reencrypts_under_primary() -> None:
    old_key = generate_key()
    new_key = generate_key()
    old_cipher = CredentialCipher.from_key_material(old_key)
    encrypted_old = old_cipher.encrypt("client-secret")
    # A cipher with the new key primary + old key retired can still decrypt.
    rotated_cipher = CredentialCipher.from_key_material(new_key, retired=[old_key])
    assert rotated_cipher.decrypt(encrypted_old) == "client-secret"
    reencrypted = rotated_cipher.rotate(encrypted_old)
    assert CredentialCipher.from_key_material(new_key).decrypt(reencrypted) == "client-secret"


async def test_credential_store_persists_encrypted_and_loads_plaintext(
    ctx: WorkspaceContext, tenant: uuid.UUID, connection: WorkspaceConnection
) -> None:
    from pb_api.integrations.workspace.ports.credentials import OAuthGrant

    await ctx.credential_store.save(
        OAuthGrant(
            tenant_id=tenant,
            connection_id=connection.id,
            provider_tenant_id="contoso",
            client_id="app-123",
            client_secret="the-secret",
            refresh_token="the-refresh",
            scopes=["Mail.Read"],
        )
    )
    # The stored row holds ciphertext, never the plaintext secret.
    row = await ctx.credentials.get(tenant, connection.id)
    assert row is not None
    assert row.client_secret_encrypted != "the-secret"
    assert row.refresh_token_encrypted not in (None, "the-refresh")
    # The store decrypts on load.
    grant = await ctx.credential_store.load(tenant, connection.id)
    assert grant is not None
    assert grant.client_secret == "the-secret"
    assert grant.refresh_token == "the-refresh"


async def test_credential_store_tenant_isolated(
    session: AsyncSession,
    ctx: WorkspaceContext,
    tenant: uuid.UUID,
    other_tenant: uuid.UUID,
    connection: WorkspaceConnection,
) -> None:
    from pb_api.integrations.workspace.ports.credentials import OAuthGrant

    await ctx.credential_store.save(
        OAuthGrant(
            tenant_id=tenant,
            connection_id=connection.id,
            client_id="app",
            client_secret="s",
        )
    )
    assert await ctx.credential_store.load(other_tenant, connection.id) is None
