"""Recipe and token routes."""

from typing import Any

from fastapi.testclient import TestClient

RECIPE: dict[str, Any] = {
    "title": "Perinteinen mansikkakakku",
    "category": "cake",
    "language": "fi",
    "instructions_md": "1. Bake the base\n2. Whip the cream\n3. Assemble",
    "servings": 12,
    "yield_text": "15 palaa",
    "total_time_minutes": 180,
    "ingredients": [
        {"raw_text": "5 munan sokerikakkupohja TAI"},
        {"raw_text": "5 munan gluteeniton kakkupohja", "alternative_of": 0},
        {"raw_text": "2 dl kermaa", "qty": 2.0, "unit": "dl", "item": "kermaa"},
    ],
    "tags": ["Summer", "party"],
}


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/recipes", json={**RECIPE, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


# ─── access control ──────────────────────────────────────────────────────


def test_every_recipe_route_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/recipes").status_code == 401
    assert client.post("/api/recipes", json=RECIPE).status_code == 401
    assert client.get("/api/recipes/1").status_code == 401
    assert client.patch("/api/recipes/1", json={"title": "x"}).status_code == 401
    assert client.delete("/api/recipes/1").status_code == 401


# ─── create and read ─────────────────────────────────────────────────────


def test_create_round_trips_everything(auth_client: TestClient) -> None:
    created = _create(auth_client)
    fetched = auth_client.get(f"/api/recipes/{created['id']}").json()

    assert fetched["title"] == RECIPE["title"]
    assert fetched["category"] == "cake"
    assert fetched["servings"] == 12
    assert fetched["yield_text"] == "15 palaa"
    assert fetched["source_platform"] == "manual"
    assert [line["raw_text"] for line in fetched["ingredients"]] == [
        line["raw_text"] for line in RECIPE["ingredients"]
    ]
    assert fetched["ingredients"][1]["alternative_of"] == 0
    assert fetched["ingredients"][2]["qty"] == 2.0
    assert fetched["tags"] == ["party", "summer"]


def test_unknown_category_is_refused(auth_client: TestClient) -> None:
    response = auth_client.post("/api/recipes", json={**RECIPE, "category": "pudding"})
    assert response.status_code == 422


def test_categories_endpoint_lists_the_vocabulary(auth_client: TestClient) -> None:
    body = auth_client.get("/api/recipes/categories").json()
    keys = {row["key"] for row in body}
    assert {"main_course", "cake", "bread", "dessert"} <= keys
    assert all(row["colour"].startswith("#") for row in body)


def test_missing_recipe_is_404(auth_client: TestClient) -> None:
    assert auth_client.get("/api/recipes/9999").status_code == 404


# ─── update ──────────────────────────────────────────────────────────────


def test_patch_changes_only_supplied_fields(auth_client: TestClient) -> None:
    created = _create(auth_client)
    patched = auth_client.patch(f"/api/recipes/{created['id']}", json={"title": "Renamed"}).json()

    assert patched["title"] == "Renamed"
    assert patched["servings"] == 12
    assert len(patched["ingredients"]) == 3


def test_patching_ingredients_replaces_the_whole_list(auth_client: TestClient) -> None:
    created = _create(auth_client)
    patched = auth_client.patch(
        f"/api/recipes/{created['id']}",
        json={"ingredients": [{"raw_text": "1 dl sokeria"}]},
    ).json()

    assert [line["raw_text"] for line in patched["ingredients"]] == ["1 dl sokeria"]
    assert patched["ingredients"][0]["position"] == 0


def test_patching_tags_replaces_them(auth_client: TestClient) -> None:
    created = _create(auth_client)
    patched = auth_client.patch(f"/api/recipes/{created['id']}", json={"tags": ["winter"]}).json()
    assert patched["tags"] == ["winter"]


def test_empty_patch_is_harmless(auth_client: TestClient) -> None:
    created = _create(auth_client)
    response = auth_client.patch(f"/api/recipes/{created['id']}", json={})
    assert response.status_code == 200
    assert response.json()["title"] == RECIPE["title"]


# ─── favourite and delete ────────────────────────────────────────────────


def test_favourite_toggles(auth_client: TestClient) -> None:
    created = _create(auth_client)
    assert created["is_favourite"] is False
    assert auth_client.post(f"/api/recipes/{created['id']}/favourite").json()["is_favourite"]
    assert not auth_client.post(f"/api/recipes/{created['id']}/favourite").json()["is_favourite"]


def test_delete_removes_it(auth_client: TestClient) -> None:
    created = _create(auth_client)
    assert auth_client.delete(f"/api/recipes/{created['id']}").status_code == 204
    assert auth_client.get(f"/api/recipes/{created['id']}").status_code == 404
    assert auth_client.delete(f"/api/recipes/{created['id']}").status_code == 404


# ─── listing and filters ─────────────────────────────────────────────────


def test_filters_compose(auth_client: TestClient) -> None:
    cake = _create(auth_client)
    _create(auth_client, title="Shanghai taco salad", category="salad", tags=["quick"])
    auth_client.post(f"/api/recipes/{cake['id']}/favourite")

    def titles(**params: Any) -> list[str]:
        return [r["title"] for r in auth_client.get("/api/recipes", params=params).json()]

    assert len(titles()) == 2
    assert titles(category="cake") == [RECIPE["title"]]
    assert titles(favourite=True) == [RECIPE["title"]]
    assert titles(tag="quick") == ["Shanghai taco salad"]
    assert titles(category="salad", favourite=True) == []


def test_search_matches_an_ingredient(auth_client: TestClient) -> None:
    _create(auth_client)
    _create(auth_client, title="Salad", ingredients=[{"raw_text": "1 lime"}], tags=[])
    found = auth_client.get("/api/recipes", params={"q": "kermaa"}).json()
    assert [r["title"] for r in found] == [RECIPE["title"]]


def test_search_survives_punctuation(auth_client: TestClient) -> None:
    """Raw text from a search box is FTS5 syntax, not a literal."""
    _create(auth_client)
    for nasty in ('"', "AND", "NEAR(", "' OR 1=1 --"):
        assert auth_client.get("/api/recipes", params={"q": nasty}).status_code == 200


# ─── device tokens ───────────────────────────────────────────────────────


def test_token_is_shown_once_and_then_only_by_metadata(auth_client: TestClient) -> None:
    created = auth_client.post("/api/tokens", json={"name": "iPhone"}).json()
    assert created["token"]

    listed = auth_client.get("/api/tokens").json()
    assert len(listed) == 1
    assert "token" not in listed[0]
    assert listed[0]["name"] == "iPhone"


def test_revoked_token_is_still_listed(auth_client: TestClient) -> None:
    created = auth_client.post("/api/tokens", json={"name": "iPhone"}).json()
    assert auth_client.delete(f"/api/tokens/{created['id']}").status_code == 204

    listed = auth_client.get("/api/tokens").json()
    assert listed[0]["revoked_at"] is not None
    # Revoking twice reports a conflict rather than silently succeeding.
    assert auth_client.delete(f"/api/tokens/{created['id']}").status_code == 409


def test_cannot_revoke_a_token_you_do_not_own(auth_client: TestClient, client: TestClient) -> None:
    """The regression test for Arboretium's admin-route privilege escalation."""
    mine = auth_client.post("/api/tokens", json={"name": "iPhone"}).json()

    other = TestClient(auth_client.app)
    other.post(
        "/api/auth/register",
        json={
            "email": "partner@example.fi",
            "password": "another-good-password",
            "display_name": "Partner",
            "site_password": "test-site-password",
        },
    )

    assert other.delete(f"/api/tokens/{mine['id']}").status_code == 404
    assert auth_client.get("/api/tokens").json()[0]["revoked_at"] is None


def test_bearer_token_is_refused_on_ordinary_routes(auth_client: TestClient) -> None:
    """Device tokens exist for POST /api/import only."""
    created = auth_client.post("/api/tokens", json={"name": "iPhone"}).json()
    bare = TestClient(auth_client.app)
    response = bare.get("/api/recipes", headers={"Authorization": f"Bearer {created['token']}"})
    assert response.status_code == 401
