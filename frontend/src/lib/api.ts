/**
 * Typed API client.
 *
 * Every request carries credentials so the session cookie travels; the PWA and
 * Safari have separate cookie jars, and the installed app must send its own.
 */
import type { ApiToken, Category, Job, Recipe, RecipeSummary, User } from "@/lib/types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: "include",
    headers: init.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // A non-JSON error body is not itself an error worth surfacing.
    }
    throw new ApiError(response.status, detail);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/auth/login", { method: "POST", body: json({ email, password }) }),
  register: (body: {
    email: string;
    password: string;
    display_name: string;
    site_password: string;
  }) => request<User>("/auth/register", { method: "POST", body: json(body) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/auth/change-password", {
      method: "POST",
      body: json({ current_password, new_password }),
    }),

  categories: () => request<Category[]>("/recipes/categories"),
  listRecipes: (params: Record<string, string | boolean | undefined> = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    const qs = search.toString();
    return request<RecipeSummary[]>(`/recipes${qs ? `?${qs}` : ""}`);
  },
  getRecipe: (id: number) => request<Recipe>(`/recipes/${id}`),
  createRecipe: (body: unknown) =>
    request<Recipe>("/recipes", { method: "POST", body: json(body) }),
  patchRecipe: (id: number, body: unknown) =>
    request<Recipe>(`/recipes/${id}`, { method: "PATCH", body: json(body) }),
  deleteRecipe: (id: number) => request<void>(`/recipes/${id}`, { method: "DELETE" }),
  toggleFavourite: (id: number) =>
    request<Recipe>(`/recipes/${id}/favourite`, { method: "POST" }),

  listJobs: () => request<Job[]>("/imports"),
  retryJob: (id: number) => request<Job>(`/imports/${id}/retry`, { method: "POST" }),
  queueImport: (url: string) =>
    request<{ job_id: number; duplicate: boolean; recipe_id: number | null }>("/import", {
      method: "POST",
      body: json({ url }),
    }),

  listTokens: () => request<ApiToken[]>("/tokens"),
  createToken: (name: string) =>
    request<ApiToken & { token: string }>("/tokens", { method: "POST", body: json({ name }) }),
  revokeToken: (id: number) => request<void>(`/tokens/${id}`, { method: "DELETE" }),

  pushKey: () => request<{ key: string }>("/push/key"),
  pushSubscribe: (subscription: unknown) =>
    request<{ id: number }>("/push/subscribe", { method: "POST", body: json(subscription) }),
};
