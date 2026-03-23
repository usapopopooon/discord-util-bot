import { describe, it, expect } from "vitest";
import { cn } from "../utils";

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("handles conditional classes", () => {
    expect(cn("base", false && "hidden", "extra")).toBe("base extra");
    expect(cn("base", true && "visible", "extra")).toBe("base visible extra");
  });

  it("handles undefined and null inputs", () => {
    expect(cn("base", undefined, null, "extra")).toBe("base extra");
  });

  it("returns empty string for no inputs", () => {
    expect(cn()).toBe("");
  });

  it("merges tailwind classes correctly (last wins)", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("handles arrays of classes", () => {
    expect(cn(["foo", "bar"], "baz")).toBe("foo bar baz");
  });

  it("handles object syntax", () => {
    expect(cn({ hidden: true, visible: false })).toBe("hidden");
    expect(cn({ hidden: false, visible: true })).toBe("visible");
  });
});
