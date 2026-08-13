import { describe, expect, it } from "vitest";

import { deriveSteps, formatQuantity, scaleLine, scaleQuantity } from "@/lib/steps";

describe("deriveSteps", () => {
  it("splits a numbered list", () => {
    expect(deriveSteps("1. Heat the oven\n2. Mix the flour\n3. Bake")).toEqual([
      "Heat the oven",
      "Mix the flour",
      "Bake",
    ]);
  });

  it("splits a bulleted list", () => {
    expect(deriveSteps("- Heat the oven\n- Bake")).toEqual(["Heat the oven", "Bake"]);
  });

  it("yields one step for a single paragraph", () => {
    // Correct behaviour, not a bug: some recipes really are one paragraph.
    expect(deriveSteps("Heat the oven and bake for 20 minutes.")).toEqual([
      "Heat the oven and bake for 20 minutes.",
    ]);
  });

  it("splits paragraphs when there are no list markers", () => {
    expect(deriveSteps("First do this.\n\nThen do that.")).toEqual([
      "First do this.",
      "Then do that.",
    ]);
  });

  it("ignores headings", () => {
    const steps = deriveSteps("## Base\n\n1. Whisk the eggs\n2. Fold in flour");
    expect(steps).toEqual(["Whisk the eggs", "Fold in flour"]);
  });

  it("returns nothing for empty instructions", () => {
    expect(deriveSteps("")).toEqual([]);
    expect(deriveSteps("   \n\n  ")).toEqual([]);
  });
});

describe("scaleQuantity", () => {
  it("doubles cleanly", () => {
    expect(scaleQuantity(2, 4, 8)).toBe(4);
    expect(scaleQuantity(200, 4, 8)).toBe(400);
  });

  it("rounds to something measurable", () => {
    // Nobody weighs 1.3333 eggs.
    expect(scaleQuantity(2, 3, 4)).toBe(2.75);
    expect(scaleQuantity(1, 3, 4)).toBe(1.25);
  });

  it("rounds large amounts to the nearest five", () => {
    expect(scaleQuantity(200, 3, 4)).toBe(265);
  });

  it("is a no-op for a nonsense serving count", () => {
    expect(scaleQuantity(2, 0, 4)).toBe(2);
    expect(scaleQuantity(2, 4, 0)).toBe(2);
  });
});

describe("scaleLine", () => {
  it("rewrites the leading quantity", () => {
    expect(scaleLine("2 dl kermaa", 2, 4, 8)).toBe("4 dl kermaa");
  });

  it("leaves a raw-only line untouched", () => {
    // Inventing a number is worse than leaving it alone.
    expect(scaleLine("a pinch of salt", null, 4, 8)).toBe("a pinch of salt");
  });

  it("is a no-op at the original serving count", () => {
    expect(scaleLine("2 dl kermaa", 2, 4, 4)).toBe("2 dl kermaa");
  });

  it("does not touch a number that belongs to the product", () => {
    // "400 g" names the tin, not the amount to use.
    expect(scaleLine("1 prk (400 g) tomaattimurskaa", 1, 4, 8)).toBe(
      "2 prk (400 g) tomaattimurskaa",
    );
  });
});

describe("formatQuantity", () => {
  it("drops trailing zeroes", () => {
    expect(formatQuantity(4)).toBe("4");
    expect(formatQuantity(2.5)).toBe("2.5");
    expect(formatQuantity(2.25)).toBe("2.25");
  });
});
