import { EmptyState } from "@/components/ui/card";
import { t } from "@/lib/strings";

/** The Imports screen. Job list and retry arrive in Phase 5. */
export function Imports() {
  return (
    <EmptyState
      title="No imports yet"
      body="Share a recipe link from your phone and it will appear here."
    />
  );
}

export { t };
