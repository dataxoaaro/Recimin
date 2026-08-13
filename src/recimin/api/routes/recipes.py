"""Recipe CRUD."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from recimin.api.deps import CurrentUser, DbDep
from recimin.api.schemas import (
    CategoryOut,
    IngredientOut,
    RecipeIn,
    RecipeOut,
    RecipePatch,
    RecipeSummary,
)
from recimin.db.categories import CATEGORY_META, Category
from recimin.db.models import Recipe, RecipeStatus
from recimin.db.repositories import ingredients as ing_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.db.repositories import tags as tags_repo
from recimin.db.repositories.ingredients import IngredientDraft
from recimin.db.repositories.recipes import RecipeDraft

router = APIRouter(prefix="/recipes", tags=["recipes"])

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")


def _to_drafts(lines: list[IngredientOut] | list) -> list[IngredientDraft]:
    return [
        IngredientDraft(
            raw_text=line.raw_text,
            original_text=line.original_text,
            qty=line.qty,
            unit=line.unit,
            item=line.item,
            note=line.note,
            group_label=line.group_label,
            alternative_of=line.alternative_of,
        )
        for line in lines
    ]


def _summary(recipe: Recipe) -> RecipeSummary:
    return RecipeSummary(
        id=recipe.id,
        title=recipe.title,
        category=recipe.category,
        language=recipe.language,
        is_favourite=recipe.is_favourite,
        status=recipe.status,
        total_time_minutes=recipe.total_time_minutes,
        servings=recipe.servings,
        hero_media_id=recipe.hero_media_id,
        source_platform=recipe.source_platform,
        created_at=recipe.created_at,
    )


def _full(conn: sqlite3.Connection, recipe: Recipe) -> RecipeOut:
    lines = ing_repo.for_recipe(conn, recipe.id)
    return RecipeOut(
        **_summary(recipe).model_dump(),
        description=recipe.description,
        instructions_md=recipe.instructions_md,
        notes=recipe.notes,
        yield_text=recipe.yield_text,
        source_url=recipe.source_url,
        source_site=recipe.source_site,
        source_author=recipe.source_author,
        source_title=recipe.source_title,
        imported_at=recipe.imported_at,
        updated_at=recipe.updated_at,
        ingredients=[
            IngredientOut(
                position=line.position,
                raw_text=line.raw_text,
                original_text=line.original_text,
                qty=line.qty,
                unit=line.unit,
                item=line.item,
                note=line.note,
                group_label=line.group_label,
                alternative_of=line.alternative_of,
            )
            for line in lines
        ],
        tags=tags_repo.for_recipe(conn, recipe.id),
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories() -> list[CategoryOut]:
    """The fixed category vocabulary, for filter chips and the edit form."""
    return [
        CategoryOut(key=str(key), label=meta.label, colour=meta.colour)
        for key, meta in CATEGORY_META.items()
    ]


@router.get("", response_model=list[RecipeSummary])
def list_recipes(
    _: CurrentUser,
    conn: DbDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: str | None = None,
    tag: str | None = None,
    favourite: bool | None = None,
    recipe_status: Annotated[RecipeStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RecipeSummary]:
    """Filtered library listing, newest first."""
    found = recipes_repo.list_recipes(
        conn,
        query=q,
        category=category,
        tag=tag,
        favourite=favourite,
        status=recipe_status,
        limit=limit,
        offset=offset,
    )
    return [_summary(recipe) for recipe in found]


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(body: RecipeIn, _: CurrentUser, conn: DbDep) -> RecipeOut:
    """Create a recipe by hand."""
    if body.category not in {str(c) for c in Category}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown category")

    recipe_id = recipes_repo.create(
        conn,
        RecipeDraft(
            title=body.title,
            instructions_md=body.instructions_md,
            category=body.category,
            language=body.language,
            status=body.status,
            description=body.description,
            notes=body.notes,
            servings=body.servings,
            yield_text=body.yield_text,
            total_time_minutes=body.total_time_minutes,
            source_platform="manual",  # type: ignore[arg-type]
        ),
        ingredient_lines=_to_drafts(body.ingredients),
        tag_names=body.tags,
    )
    recipe = recipes_repo.get(conn, recipe_id)
    if recipe is None:  # pragma: no cover - defensive
        raise NOT_FOUND
    return _full(conn, recipe)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, _: CurrentUser, conn: DbDep) -> RecipeOut:
    """One recipe with its ingredients and tags."""
    recipe = recipes_repo.get(conn, recipe_id)
    if recipe is None:
        raise NOT_FOUND
    return _full(conn, recipe)


@router.patch("/{recipe_id}", response_model=RecipeOut)
def patch_recipe(recipe_id: int, body: RecipePatch, _: CurrentUser, conn: DbDep) -> RecipeOut:
    """Partial update. An ingredients array replaces the whole list."""
    if recipes_repo.get(conn, recipe_id) is None:
        raise NOT_FOUND

    payload = body.model_dump(exclude_unset=True)
    lines = payload.pop("ingredients", None)
    tag_names = payload.pop("tags", None)

    if payload.get("category") is not None and payload["category"] not in {
        str(c) for c in Category
    }:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown category")

    if payload:
        recipes_repo.update(conn, recipe_id, **payload)
    if lines is not None:
        ing_repo.replace_all(
            conn,
            recipe_id,
            _to_drafts([IngredientOut(position=i, **line) for i, line in enumerate(lines)]),
        )
    if tag_names is not None:
        tags_repo.set_for_recipe(conn, recipe_id, tag_names)

    recipe = recipes_repo.get(conn, recipe_id)
    if recipe is None:  # pragma: no cover - defensive
        raise NOT_FOUND
    return _full(conn, recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: int, _: CurrentUser, conn: DbDep) -> None:
    """Delete a recipe. Ingredients, tags and media cascade."""
    if not recipes_repo.delete(conn, recipe_id):
        raise NOT_FOUND


@router.post("/{recipe_id}/favourite", response_model=RecipeOut)
def toggle_favourite(recipe_id: int, _: CurrentUser, conn: DbDep) -> RecipeOut:
    """Flip the favourite flag."""
    recipe = recipes_repo.get(conn, recipe_id)
    if recipe is None:
        raise NOT_FOUND
    recipes_repo.set_favourite(conn, recipe_id, not recipe.is_favourite)
    updated = recipes_repo.get(conn, recipe_id)
    if updated is None:  # pragma: no cover - defensive
        raise NOT_FOUND
    return _full(conn, updated)
