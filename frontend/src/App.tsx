import * as React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { AuthGuard } from "@/components/AuthGuard";
import { AuthProvider } from "@/lib/auth-context";
import { Library } from "@/routes/Library";
import { SignIn } from "@/routes/SignIn";

/**
 * Library and SignIn are eager: one of them is always the first paint.
 *
 * Everything else is split out. The single bundle was 430 kB, and most of it
 * was reachable from routes a cold visitor never opens — react-markdown and
 * its remark/micromark chain are pulled in only by the recipe and cook views,
 * and the styleguide is a development page that was being shipped to phones.
 */
const RecipeDetail = React.lazy(() =>
  import("@/routes/RecipeDetail").then((m) => ({ default: m.RecipeDetail })),
);
const CookMode = React.lazy(() =>
  import("@/routes/CookMode").then((m) => ({ default: m.CookMode })),
);
const Imports = React.lazy(() => import("@/routes/Imports").then((m) => ({ default: m.Imports })));
const Settings = React.lazy(() =>
  import("@/routes/Settings").then((m) => ({ default: m.Settings })),
);
const Register = React.lazy(() =>
  import("@/routes/Register").then((m) => ({ default: m.Register })),
);
const StyleGuide = React.lazy(() =>
  import("@/routes/StyleGuide").then((m) => ({ default: m.StyleGuide })),
);

/**
 * Deliberately blank rather than a spinner. These chunks are a few kB over a
 * warm connection; a spinner that flashes for 80ms reads as jank, not progress.
 */
const PENDING = <div className="min-h-24" aria-busy="true" />;

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <React.Suspense fallback={PENDING}>
          <Routes>
            <Route path="/sign-in" element={<SignIn />} />
            <Route path="/register" element={<Register />} />
            <Route path="/styleguide" element={<StyleGuide />} />
            <Route
              element={
                <AuthGuard>
                  <AppShell />
                </AuthGuard>
              }
            >
              <Route index element={<Library />} />
              <Route path="recipes/:id" element={<RecipeDetail />} />
              <Route path="recipes/:id/cook" element={<CookMode />} />
              <Route path="imports" element={<Imports />} />
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </React.Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}
