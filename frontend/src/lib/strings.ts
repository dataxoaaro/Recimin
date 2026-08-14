/**
 * All user-facing copy.
 *
 * Voice, inherited from Arboretium: one- or two-word imperative labels;
 * sentences only where the user must be told something; progress states get
 * their own present-continuous label ending in a real ellipsis; errors are
 * short, blameless and uniform. No exclamation marks, no emoji, no jokes.
 *
 * Centralised so a Finnish translation is a swap rather than a refactor.
 */
export const t = {
  appName: "Recimin",
  tagline: "Every recipe you saved, in one place.",

  // actions
  save: "Save",
  saving: "Saving…",
  adding: "Adding…",
  cancel: "Cancel",
  del: "Delete",
  edit: "Edit",
  close: "Close",
  retry: "Retry",
  add: "Add",
  done: "Done",
  cook: "Cook",
  favourite: "Favourite",
  signIn: "Sign in",
  signingIn: "Signing in…",
  signOut: "Sign out",
  register: "Create account",
  registering: "Creating account…",

  // navigation
  library: "Library",
  imports: "Imports",
  settings: "Settings",

  // states
  loading: "Loading…",
  // "Check", not "Draft". The badge now marks a recipe the model was unsure
  // about, so it should say what to do rather than name an internal state.
  draft: "Check",
  reviewTitle: "Read this one over",
  reviewBody: "The importer was not confident. Check the amounts against the source.",
  reviewConfirm: "Looks right",

  // library
  libraryEmptyTitle: "No recipes yet",
  libraryEmptyBody: "Add one with the + button, or share a link from your phone.",
  searchPlaceholder: "Search recipes",
  searchEmptyTitle: "Nothing found",
  searchEmptyBody: "Try a different word, or clear the filters.",
  allCategories: "All",
  minutes: (n: number) => `${n} min`,
  servings: (n: number) => `${n} servings`,

  // auth
  email: "Email",
  password: "Password",
  displayName: "Name",
  sitePassword: "Site password",
  sitePasswordHint: "Ask whoever set this up if you do not have it.",
  passwordRule: "Password (at least 10 characters)",
  noAccount: "Do not have an account?",
  haveAccount: "Already have an account?",
  changePassword: "Change password",
  currentPassword: "Current password",
  newPasswordRule: "New password (at least 10 characters)",
  passwordChanged: "Password changed",

  // imports
  alreadySaved: "Already saved",

  // errors — noun plus "failed", no codes, no apology
  signInFailed: "Incorrect email or password",
  saveFailed: "Save failed",
  loadFailed: "Loading failed",
  deleteFailed: "Delete failed",
  importFailed: "Import failed",
  wrongCurrentPassword: "Incorrect current password",
  tooManyAttempts: "Too many attempts. Try again later.",
} as const;
