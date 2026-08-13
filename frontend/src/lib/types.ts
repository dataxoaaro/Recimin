/** Shapes mirroring the API's response models. */

export interface User {
  id: number;
  email: string;
  display_name: string;
}

export interface Category {
  key: string;
  label: string;
  colour: string;
}

export interface Ingredient {
  position: number;
  raw_text: string;
  original_text: string | null;
  qty: number | null;
  unit: string | null;
  item: string | null;
  note: string | null;
  group_label: string | null;
  alternative_of: number | null;
}

export interface RecipeSummary {
  id: number;
  title: string;
  category: string;
  language: string;
  is_favourite: boolean;
  status: "draft" | "published";
  total_time_minutes: number | null;
  servings: number | null;
  hero_media_id: number | null;
  source_platform: string | null;
  created_at: string;
}

export interface Recipe extends RecipeSummary {
  description: string | null;
  instructions_md: string;
  notes: string | null;
  yield_text: string | null;
  source_url: string | null;
  source_site: string | null;
  source_author: string | null;
  source_title: string | null;
  imported_at: string | null;
  updated_at: string;
  ingredients: Ingredient[];
  tags: string[];
}

export interface Job {
  id: number;
  status: "queued" | "running" | "done" | "failed" | "needs_attention";
  stage: string | null;
  input_url: string;
  normalised_url: string | null;
  platform: string | null;
  recipe_id: number | null;
  attempts: number;
  last_error: string | null;
  caption_gate: "hit" | "miss" | null;
  created_at: string;
  finished_at: string | null;
}

export interface ApiToken {
  id: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
