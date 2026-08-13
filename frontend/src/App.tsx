import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { AuthGuard } from "@/components/AuthGuard";
import { AuthProvider } from "@/lib/auth-context";
import { Imports } from "@/routes/Imports";
import { Library } from "@/routes/Library";
import { Register } from "@/routes/Register";
import { Settings } from "@/routes/Settings";
import { SignIn } from "@/routes/SignIn";
import { StyleGuide } from "@/routes/StyleGuide";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
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
            <Route path="imports" element={<Imports />} />
            <Route path="settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
