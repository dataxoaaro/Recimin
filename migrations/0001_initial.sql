-- Recimin initial schema.
-- See claudedocs/recimin-technical.md section 4.

-- ─── identity ────────────────────────────────────────────────────────────

CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name  TEXT NOT NULL,
  created_at    TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_users_email_lower ON users (lower(email));

-- Device bearer tokens for the iOS Shortcut. The Shortcut cannot perform a
-- cookie login flow, and an installed PWA's cookie jar is separate from Safari's.
CREATE TABLE api_tokens (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  token_hash   TEXT NOT NULL UNIQUE,
  created_at   TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at   TEXT
);

CREATE INDEX idx_api_tokens_user ON api_tokens(user_id);

-- ─── media ───────────────────────────────────────────────────────────────
-- media.recipe_id and recipes.hero_media_id form a legal circular reference.
-- SQLite resolves foreign keys at runtime, not at DDL time, so the forward
-- reference below is fine. Insert order is: recipe first, then media, then set
-- hero_media_id.

CREATE TABLE media (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id    INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL CHECK (kind IN ('image','video','audio','frame')),
  position     INTEGER NOT NULL DEFAULT 0,
  file_path    TEXT NOT NULL UNIQUE,
  sha256       TEXT NOT NULL,
  bytes        INTEGER NOT NULL,
  mime         TEXT NOT NULL,
  width        INTEGER,
  height       INTEGER,
  duration_s   REAL,
  source_url   TEXT,
  created_at   TEXT NOT NULL,
  -- File deleted, row retained: import must never re-download a discarded item.
  discarded_at TEXT
);

CREATE INDEX idx_media_recipe ON media(recipe_id, kind, position);
CREATE INDEX idx_media_sha256 ON media(sha256);

-- ─── recipes ─────────────────────────────────────────────────────────────

CREATE TABLE recipes (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  title              TEXT NOT NULL,
  description        TEXT,
  -- Markdown blob. Cook mode derives its stepper at render time by splitting on
  -- list items and numbered lines; no migration is needed to gain step tracking.
  instructions_md    TEXT NOT NULL DEFAULT '',
  notes              TEXT,
  servings           INTEGER,
  yield_text         TEXT,
  total_time_minutes INTEGER,
  category           TEXT NOT NULL DEFAULT 'main_course',
  language           TEXT NOT NULL DEFAULT 'en',
  is_favourite       INTEGER NOT NULL DEFAULT 0 CHECK (is_favourite IN (0,1)),
  status             TEXT NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','published')),
  hero_media_id      INTEGER REFERENCES media(id) ON DELETE SET NULL,

  source_url            TEXT,
  source_url_normalised TEXT,
  source_site           TEXT,
  source_author         TEXT,
  source_title          TEXT,
  source_platform       TEXT CHECK (source_platform IN
                          ('web','instagram','tiktok','youtube','manual')),
  imported_at        TEXT,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);

-- Partial index: one recipe per source URL, while permitting many manually
-- created recipes that have no source at all.
CREATE UNIQUE INDEX idx_recipes_source
  ON recipes(source_url_normalised) WHERE source_url_normalised IS NOT NULL;

CREATE INDEX idx_recipes_category  ON recipes(category);
CREATE INDEX idx_recipes_status    ON recipes(status);
CREATE INDEX idx_recipes_favourite ON recipes(is_favourite) WHERE is_favourite = 1;
CREATE INDEX idx_recipes_created   ON recipes(created_at DESC);

-- ─── ingredients ─────────────────────────────────────────────────────────
-- raw_text is the source of truth and is always what gets displayed.
-- The parsed columns are opportunistic; NULL is normal and never an error.

CREATE TABLE ingredients (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id      INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  position       INTEGER NOT NULL,
  raw_text       TEXT NOT NULL,
  -- Pre-conversion line, retained whenever units were normalised, so a bad
  -- conversion is visible in the review UI rather than silent.
  original_text  TEXT,
  qty            REAL,
  unit           TEXT,
  item           TEXT,
  note           TEXT,
  group_label    TEXT,
  -- Position of the line this substitutes for. Finnish recipes write
  -- "5 munan sokerikakkupohja TAI" / "5 munan gluteeniton kakkupohja" as one
  -- choice across two lines; without this a shopping list would buy both.
  alternative_of INTEGER,
  UNIQUE (recipe_id, position)
);

CREATE INDEX idx_ingredients_recipe ON ingredients(recipe_id, position);

-- ─── tags ────────────────────────────────────────────────────────────────

CREATE TABLE tags (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE recipe_tags (
  recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
  tag_id    INTEGER NOT NULL REFERENCES tags(id)    ON DELETE CASCADE,
  PRIMARY KEY (recipe_id, tag_id)
);

CREATE INDEX idx_recipe_tags_tag ON recipe_tags(tag_id);

-- ─── jobs ────────────────────────────────────────────────────────────────
-- The only channel between the api and worker containers.

CREATE TABLE jobs (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  kind           TEXT NOT NULL DEFAULT 'import',
  status         TEXT NOT NULL CHECK (status IN
                   ('queued','running','done','failed','needs_attention')),
  stage          TEXT,
  input_url      TEXT NOT NULL,
  normalised_url TEXT,
  platform       TEXT,
  recipe_id      INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
  attempts       INTEGER NOT NULL DEFAULT 0,
  last_error     TEXT,
  -- Instrumentation: did the caption alone carry the recipe? No published data
  -- exists on this, so measure our own.
  caption_gate   TEXT CHECK (caption_gate IN ('hit','miss')),
  created_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at     TEXT NOT NULL,
  started_at     TEXT,
  finished_at    TEXT
);

CREATE INDEX idx_jobs_status ON jobs(status, created_at);

-- ─── push ────────────────────────────────────────────────────────────────

CREATE TABLE push_subscriptions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  endpoint   TEXT NOT NULL UNIQUE,
  p256dh     TEXT NOT NULL,
  auth       TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- ─── search ──────────────────────────────────────────────────────────────
-- A content-storing FTS5 table keyed by rowid = recipes.id.
--
-- Not contentless: `content=''` forbids a plain DELETE, so every removal would
-- need the original column values replayed. At a few hundred recipes the
-- duplicated text costs nothing and DELETE ... WHERE rowid = ? just works.
--
-- Instructions are deliberately excluded: matching "add the flour" is noise.

CREATE VIRTUAL TABLE recipes_fts USING fts5(
  title,
  ingredients,
  tags,
  tokenize='unicode61 remove_diacritics 2'
);

-- Reindex a single recipe from its current state. Ingredients and tags live in
-- other tables, so every trigger recomputes the whole row rather than trying to
-- patch it. Triggers rather than repository calls: a sync you can forget to call
-- is a sync that drifts.

CREATE TRIGGER trg_recipes_fts_ai AFTER INSERT ON recipes BEGIN
  INSERT INTO recipes_fts(rowid, title, ingredients, tags)
    VALUES (new.id, new.title, '', '');
END;

CREATE TRIGGER trg_recipes_fts_au AFTER UPDATE OF title ON recipes BEGIN
  DELETE FROM recipes_fts WHERE rowid = new.id;
  INSERT INTO recipes_fts(rowid, title, ingredients, tags)
    SELECT new.id, new.title,
           coalesce((SELECT group_concat(i.raw_text, ' ')
                       FROM ingredients i WHERE i.recipe_id = new.id), ''),
           coalesce((SELECT group_concat(t.name, ' ')
                       FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id
                      WHERE rt.recipe_id = new.id), '');
END;

CREATE TRIGGER trg_recipes_fts_ad AFTER DELETE ON recipes BEGIN
  DELETE FROM recipes_fts WHERE rowid = OLD.id;
END;

CREATE TRIGGER trg_ingredients_fts_ai AFTER INSERT ON ingredients BEGIN
  DELETE FROM recipes_fts WHERE rowid = new.recipe_id;
  INSERT INTO recipes_fts(rowid, title, ingredients, tags)
    SELECT r.id, r.title,
           coalesce((SELECT group_concat(i.raw_text, ' ')
                       FROM ingredients i WHERE i.recipe_id = r.id), ''),
           coalesce((SELECT group_concat(t.name, ' ')
                       FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id
                      WHERE rt.recipe_id = r.id), '')
      FROM recipes r WHERE r.id = new.recipe_id;
END;

CREATE TRIGGER trg_ingredients_fts_au AFTER UPDATE ON ingredients BEGIN
  DELETE FROM recipes_fts WHERE rowid = new.recipe_id;
  INSERT INTO recipes_fts(rowid, title, ingredients, tags)
    SELECT r.id, r.title,
           coalesce((SELECT group_concat(i.raw_text, ' ')
                       FROM ingredients i WHERE i.recipe_id = r.id), ''),
           coalesce((SELECT group_concat(t.name, ' ')
                       FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id
                      WHERE rt.recipe_id = r.id), '')
      FROM recipes r WHERE r.id = new.recipe_id;
END;

-- Guarded by the recipe still existing: ON DELETE CASCADE fires this trigger
-- once per ingredient row while the parent recipe is already gone.
CREATE TRIGGER trg_ingredients_fts_ad AFTER DELETE ON ingredients BEGIN
  DELETE FROM recipes_fts WHERE rowid = OLD.recipe_id;
  INSERT INTO recipes_fts(rowid, title, ingredients, tags)
    SELECT r.id, r.title,
           coalesce((SELECT group_concat(i.raw_text, ' ')
                       FROM ingredients i WHERE i.recipe_id = r.id), ''),
           coalesce((SELECT group_concat(t.name, ' ')
                       FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id
                      WHERE rt.recipe_id = r.id), '')
      FROM recipes r WHERE r.id = OLD.recipe_id;
END;

CREATE TRIGGER trg_recipe_tags_fts_ai AFTER INSERT ON recipe_tags BEGIN
  DELETE FROM recipes_fts WHERE rowid = new.recipe_id;
  INSERT INTO recipes_fts(rowid, title, ingredients, tags)
    SELECT r.id, r.title,
           coalesce((SELECT group_concat(i.raw_text, ' ')
                       FROM ingredients i WHERE i.recipe_id = r.id), ''),
           coalesce((SELECT group_concat(t.name, ' ')
                       FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id
                      WHERE rt.recipe_id = r.id), '')
      FROM recipes r WHERE r.id = new.recipe_id;
END;

CREATE TRIGGER trg_recipe_tags_fts_ad AFTER DELETE ON recipe_tags BEGIN
  DELETE FROM recipes_fts WHERE rowid = OLD.recipe_id;
  INSERT INTO recipes_fts(rowid, title, ingredients, tags)
    SELECT r.id, r.title,
           coalesce((SELECT group_concat(i.raw_text, ' ')
                       FROM ingredients i WHERE i.recipe_id = r.id), ''),
           coalesce((SELECT group_concat(t.name, ' ')
                       FROM recipe_tags rt JOIN tags t ON t.id = rt.tag_id
                      WHERE rt.recipe_id = r.id), '')
      FROM recipes r WHERE r.id = OLD.recipe_id;
END;
