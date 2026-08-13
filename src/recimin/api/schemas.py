"""Request and response models.

Validation happens here, at the system boundary. Nothing downstream re-checks.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from recimin.api.auth import MIN_PASSWORD_LENGTH
from recimin.db.models import CaptionGate, JobStage, JobStatus, RecipeStatus, SourcePlatform

# ─── auth ────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    display_name: str = Field(min_length=1, max_length=80)
    site_password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str


# ─── tokens ──────────────────────────────────────────────────────────────


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class TokenOut(BaseModel):
    id: int
    name: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


class TokenCreatedOut(TokenOut):
    """Carries the plaintext exactly once; it is never retrievable again."""

    token: str


# ─── recipes ─────────────────────────────────────────────────────────────


class IngredientIn(BaseModel):
    raw_text: str = Field(min_length=1, max_length=500)
    original_text: str | None = Field(default=None, max_length=500)
    qty: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    item: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=200)
    group_label: str | None = Field(default=None, max_length=80)
    alternative_of: int | None = None


class IngredientOut(IngredientIn):
    position: int


class RecipeIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    instructions_md: str = Field(default="", max_length=50_000)
    category: str = "main_course"
    language: str = Field(default="en", pattern="^(fi|en)$")
    description: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=10_000)
    servings: int | None = Field(default=None, ge=1, le=999)
    yield_text: str | None = Field(default=None, max_length=80)
    total_time_minutes: int | None = Field(default=None, ge=0, le=100_000)
    status: RecipeStatus = RecipeStatus.PUBLISHED
    ingredients: list[IngredientIn] = Field(default_factory=list, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=20)


class RecipePatch(BaseModel):
    """Partial update. Only supplied fields change.

    An ingredients array, when present, replaces the whole list.
    """

    title: str | None = Field(default=None, min_length=1, max_length=300)
    instructions_md: str | None = Field(default=None, max_length=50_000)
    category: str | None = None
    language: str | None = Field(default=None, pattern="^(fi|en)$")
    description: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=10_000)
    servings: int | None = Field(default=None, ge=1, le=999)
    yield_text: str | None = Field(default=None, max_length=80)
    total_time_minutes: int | None = Field(default=None, ge=0, le=100_000)
    status: RecipeStatus | None = None
    is_favourite: bool | None = None
    hero_media_id: int | None = None
    ingredients: list[IngredientIn] | None = Field(default=None, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=20)


class RecipeSummary(BaseModel):
    id: int
    title: str
    category: str
    language: str
    is_favourite: bool
    status: RecipeStatus
    total_time_minutes: int | None
    servings: int | None
    hero_media_id: int | None
    source_platform: SourcePlatform | None
    created_at: str


class RecipeOut(RecipeSummary):
    description: str | None
    instructions_md: str
    notes: str | None
    yield_text: str | None
    source_url: str | None
    source_site: str | None
    source_author: str | None
    source_title: str | None
    imported_at: str | None
    updated_at: str
    ingredients: list[IngredientOut]
    tags: list[str]


class CategoryOut(BaseModel):
    key: str
    label: str
    colour: str


# ─── imports ─────────────────────────────────────────────────────────────


class ImportRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class ImportAccepted(BaseModel):
    job_id: int
    duplicate: bool = False
    recipe_id: int | None = None


class JobOut(BaseModel):
    id: int
    status: JobStatus
    stage: JobStage | None
    input_url: str
    normalised_url: str | None
    platform: str | None
    recipe_id: int | None
    attempts: int
    last_error: str | None
    caption_gate: CaptionGate | None
    created_at: str
    finished_at: str | None
