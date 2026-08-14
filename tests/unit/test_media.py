"""Media storage and its routes."""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recimin.media import store

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ─── the store ───────────────────────────────────────────────────────────


def test_stores_content_addressed(tmp_path: Path) -> None:
    stored = store.store_bytes(PNG, "image/png", media_dir=tmp_path)
    digest = hashlib.sha256(PNG).hexdigest()

    assert stored.sha256 == digest
    assert stored.relative_path == f"media/{digest[:2]}/{digest}.png"
    assert (tmp_path / stored.relative_path).read_bytes() == PNG
    assert stored.deduplicated is False


def test_identical_bytes_are_written_once(tmp_path: Path) -> None:
    first = store.store_bytes(PNG, "image/png", media_dir=tmp_path)
    second = store.store_bytes(PNG, "image/png", media_dir=tmp_path)
    assert second.deduplicated is True
    assert first.relative_path == second.relative_path


def test_no_part_files_survive(tmp_path: Path) -> None:
    """Writes are temp-then-rename; a leftover .part means the rename was skipped."""
    store.store_bytes(PNG, "image/png", media_dir=tmp_path)
    assert list(tmp_path.rglob("*.part")) == []


def test_unsupported_type_is_refused(tmp_path: Path) -> None:
    with pytest.raises(store.UnsupportedMediaType):
        store.store_bytes(b"MZ", "application/x-msdownload", media_dir=tmp_path)


def test_oversized_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(store.MediaTooLarge):
        store.store_bytes(b"x" * (store.MAX_UPLOAD_BYTES + 1), "image/png", media_dir=tmp_path)


def test_path_traversal_is_refused(tmp_path: Path) -> None:
    """A stored path comes from the database, but it is still not trusted."""
    with pytest.raises(ValueError, match="escapes"):
        store.absolute_path("../../etc/passwd", media_dir=tmp_path)


def test_delete_removes_bytes_only(tmp_path: Path) -> None:
    stored = store.store_bytes(PNG, "image/png", media_dir=tmp_path)
    assert store.delete_file(stored.relative_path, media_dir=tmp_path) is True
    assert store.delete_file(stored.relative_path, media_dir=tmp_path) is False


# ─── the routes ──────────────────────────────────────────────────────────


def test_upload_and_serve_round_trip(auth_client: TestClient) -> None:
    response = auth_client.post("/api/media", files={"file": ("hero.png", PNG, "image/png")})
    assert response.status_code == 201
    media_id = response.json()["id"]

    served = auth_client.get(f"/api/media/{media_id}")
    assert served.status_code == 200
    assert served.content == PNG

    # Immutable is safe because storage is content-addressed: a media id maps
    # to a sha256-derived path, so the bytes behind an id never change and a
    # replaced photo mints a new id. At the previous max-age=300 a phone on
    # mobile data refetched every hero image it already had.
    cache_control = served.headers["cache-control"]
    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control
    # private, so the authenticated bytes are never held in a shared cache.
    assert cache_control.startswith("private")


def test_upload_refuses_an_executable(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/media", files={"file": ("evil.exe", b"MZ", "application/x-msdownload")}
    )
    assert response.status_code == 415


def test_media_requires_a_session(client: TestClient, auth_client: TestClient) -> None:
    media_id = auth_client.post(
        "/api/media", files={"file": ("hero.png", PNG, "image/png")}
    ).json()["id"]

    bare = TestClient(auth_client.app)
    assert bare.get(f"/api/media/{media_id}").status_code == 401


def test_missing_media_is_404(auth_client: TestClient) -> None:
    assert auth_client.get("/api/media/9999").status_code == 404


def test_storage_guard_returns_507(auth_client: TestClient) -> None:
    """The cap has to actually stop writes, not merely be recorded."""
    auth_client.app.state.settings = auth_client.app.state.settings.model_copy(
        update={"max_media_bytes": 10}
    )
    response = auth_client.post("/api/media", files={"file": ("hero.png", PNG, "image/png")})
    assert response.status_code == 507
