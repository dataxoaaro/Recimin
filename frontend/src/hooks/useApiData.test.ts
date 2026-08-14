import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useApiData } from "@/hooks/useApiData";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/strings";

describe("useApiData", () => {
  it("loads and exposes the data", async () => {
    const { result } = renderHook(() => useApiData(() => Promise.resolve([1, 2, 3])));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual([1, 2, 3]);
    expect(result.current.error).toBeNull();
  });

  it("surfaces the server detail for an ApiError", async () => {
    const { result } = renderHook(() =>
      useApiData<never>(() => Promise.reject(new ApiError(404, "Recipe not found"))),
    );

    await waitFor(() => expect(result.current.error).toBe("Recipe not found"));
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it("falls back to the uniform message for a network failure", async () => {
    const { result } = renderHook(() =>
      useApiData<never>(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    await waitFor(() => expect(result.current.error).toBe(t.loadFailed));
  });

  it("clears the error once a reload succeeds", async () => {
    let calls = 0;
    const flaky = () =>
      ++calls === 1 ? Promise.reject(new ApiError(500, "boom")) : Promise.resolve("fine");
    const { result } = renderHook(() => useApiData(flaky));

    await waitFor(() => expect(result.current.error).toBe("boom"));
    await act(() => result.current.reload());
    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.data).toBe("fine");
  });

  it("keeps the data identity when a reload returns an equal payload", async () => {
    const { result } = renderHook(() => useApiData(() => Promise.resolve({ jobs: [1, 2] })));

    await waitFor(() => expect(result.current.data).not.toBeNull());
    const first = result.current.data;
    await act(() => result.current.reload());
    await waitFor(() => expect(result.current.loading).toBe(false));
    // Same identity, so a polling consumer's effects keyed on the data do not churn.
    expect(result.current.data).toBe(first);
  });

  it("refetches when the fetcher changes", async () => {
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) => useApiData(() => Promise.resolve(value)),
      { initialProps: { value: "one" } },
    );

    await waitFor(() => expect(result.current.data).toBe("one"));
    rerender({ value: "two" });
    await waitFor(() => expect(result.current.data).toBe("two"));
  });
});
