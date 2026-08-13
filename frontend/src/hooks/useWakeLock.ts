import * as React from "react";

/**
 * Keep the screen awake.
 *
 * Supported in installed PWAs since iOS 16.4, and a bug that broke it
 * *specifically* in PWAs was fixed in 18.4. Two things it needs:
 *
 *   - a user gesture to acquire, which cook mode provides by being entered
 *     from a tap;
 *   - re-acquisition on visibilitychange, because iOS releases the lock when
 *     the app is backgrounded and never restores it.
 *
 * Low Power Mode can refuse outright, so every call is guarded.
 */
export function useWakeLock(active: boolean): void {
  React.useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;

    let sentinel: WakeLockSentinel | null = null;
    let cancelled = false;

    const acquire = async () => {
      try {
        sentinel = await navigator.wakeLock.request("screen");
      } catch {
        // Refused (Low Power Mode, or no permission). Not worth surfacing.
      }
    };

    const onVisible = () => {
      if (document.visibilityState === "visible" && !cancelled) void acquire();
    };

    void acquire();
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      void sentinel?.release().catch(() => {});
    };
  }, [active]);
}
