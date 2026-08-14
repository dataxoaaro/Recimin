import { describe, expect, it } from "vitest";

import { extractSharedUrl } from "@/lib/share";

const params = (init: Record<string, string>) => new URLSearchParams(init);

describe("extractSharedUrl", () => {
  it("takes the url field when it holds a link", () => {
    expect(extractSharedUrl(params({ url: "https://example.com/recipe" }))).toBe(
      "https://example.com/recipe",
    );
  });

  it("digs the link out of text when url is absent", () => {
    // The common Android share shape: the link buried in a sentence.
    expect(
      extractSharedUrl(params({ text: "Check this out https://example.com/cake yum" })),
    ).toBe("https://example.com/cake");
  });

  it("prefers url over text when both carry links", () => {
    expect(
      extractSharedUrl(
        params({ url: "https://a.example/one", text: "also https://b.example/two" }),
      ),
    ).toBe("https://a.example/one");
  });

  it("falls through to text when url holds no link", () => {
    expect(
      extractSharedUrl(params({ url: "not a link", text: "see http://example.com/soup" })),
    ).toBe("http://example.com/soup");
  });

  it("accepts plain http", () => {
    expect(extractSharedUrl(params({ url: "http://example.com" }))).toBe("http://example.com");
  });

  it("returns null when nothing shareable arrived", () => {
    expect(extractSharedUrl(params({}))).toBeNull();
    expect(extractSharedUrl(params({ title: "A nice title", text: "no link here" }))).toBeNull();
  });

  it("ignores non-http schemes", () => {
    expect(extractSharedUrl(params({ text: "ftp://example.com javascript:alert(1)" }))).toBeNull();
  });
});
