from pydantic import SecretStr
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from backend import auth


def request(token=''):
    headers=[(b'authorization',f'Bearer {token}'.encode())] if token else []
    return Request({'type':'http','headers':headers,'client':('unit-test',1234)})


def test_password_is_hashed_and_wrong_password_is_rejected():
    encoded=auth.password_hash('test-only-password')
    assert 'test-only-password' not in encoded
    assert auth.password_matches('test-only-password',encoded)
    assert not auth.password_matches('wrong',encoded)


def test_bearer_requires_valid_signature_and_expiry(monkeypatch):
    monkeypatch.setattr(auth.settings,'auth_enabled',True)
    monkeypatch.setattr(auth.settings,'auth_signing_secret',SecretStr('test-only-secret-'+('a'*40)))
    monkeypatch.setattr(auth.settings,'auth_username','unit-user')
    token=auth.serializer().dumps({'sub':'unit-user'})
    assert auth.authenticate(request(token))=='unit-user'
    for bad in ['',token+'tampered',auth.serializer().dumps({'sub':'someone-else'})]:
        with pytest.raises(HTTPException) as caught:auth.authenticate(request(bad))
        assert caught.value.status_code==401
    monkeypatch.setattr(auth.settings,'auth_ttl_seconds',-1)
    with pytest.raises(HTTPException) as caught:auth.authenticate(request(token))
    assert caught.value.status_code==401


def test_unconfigured_authentication_fails_closed(monkeypatch):
    monkeypatch.setattr(auth.settings,'auth_enabled',True)
    monkeypatch.setattr(auth.settings,'auth_signing_secret',SecretStr(''))
    with pytest.raises(RuntimeError):auth.validate_configuration()


def test_automatic_browser_sessions_are_distinct_and_renewable(monkeypatch):
    monkeypatch.setattr(auth.settings,'auth_enabled',True)
    monkeypatch.setattr(auth.settings,'auth_mode','guest')
    monkeypatch.setattr(auth.settings,'auth_signing_secret',SecretStr('browser-test-'+('x'*40)))
    first=auth.guest_session(request())['access_token']
    second=auth.guest_session(request())['access_token']
    owner=auth.authenticate(request(first));other=auth.authenticate(request(second))
    assert owner!=other
    renewed=auth.guest_session(request(first))['access_token']
    assert auth.authenticate(request(renewed))==owner
    assert auth.can_access(owner,owner)
    assert not auth.can_access(owner,other)
    assert not auth.can_access(None,owner)
    assert auth.can_access(None,auth.settings.auth_username)
    monkeypatch.setattr(auth.settings,'auth_ttl_seconds',-1)
    with pytest.raises(HTTPException):auth.authenticate(request(first))
    # An expired access session still renews the same owner within the 30-day window.
    refreshed=auth.serializer().loads(auth.guest_session(request(first))['access_token'])
    assert refreshed['sub']==owner
