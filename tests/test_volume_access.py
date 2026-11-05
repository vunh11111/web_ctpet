import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend import app as api
from backend import auth


def test_volume_endpoint_checks_browser_owner_before_reading_disk(monkeypatch,tmp_path):
    monkeypatch.setattr(auth.settings,'auth_enabled',True)
    monkeypatch.setattr(auth.settings,'auth_mode','guest')
    monkeypatch.setattr(auth.settings,'auth_signing_secret',SecretStr('volume-test-'+('x'*48)))
    first='guest:'+('a'*32);other='guest:'+('b'*32)
    tokens={owner:auth.serializer().dumps({'sub':owner,'role':'guest'}) for owner in [first,other]}
    row=SimpleNamespace(owner=first,status='completed')
    class FakeSession:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,*args):return row
    monkeypatch.setattr(api,'Session',FakeSession)
    monkeypatch.setattr(api.settings,'storage_dir',tmp_path)
    from backend import volume_preview
    calls=[]
    monkeypatch.setattr(volume_preview,'encode_volume',lambda folder,kind:(calls.append(kind) or b'fake-volume'))
    client=TestClient(api.app)
    path=f'/api/jobs/{uuid.uuid4()}/volume/ct'
    assert client.get(path).status_code==401
    assert client.get(path,headers={'Authorization':'Bearer '+tokens[other]}).status_code==404
    assert calls==[]
    # Use a non-gzip payload only to test routing; avoid response auto-decompression.
    from fastapi import HTTPException
    def marker(folder,kind):
        calls.append(kind)
        raise HTTPException(409,'owned volume handler reached')
    monkeypatch.setattr(volume_preview,'encode_volume',marker)
    assert client.get(path,headers={'Authorization':'Bearer '+tokens[first]}).status_code==409
    assert calls==['ct']
