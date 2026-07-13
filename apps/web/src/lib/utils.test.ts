import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils";

describe("cn", () => {
  it("joins multiple class names", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("ignores falsy values", () => {
    expect(cn("foo", false, null, undefined, "", "bar")).toBe("foo bar");
  });

  it("handles conditional object syntax from clsx", () => {
    expect(cn("base", { active: true, hidden: false })).toBe("base active");
  });

  it("merges conflicting tailwind classes, keeping the last one", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });

  it("keeps non-conflicting tailwind classes", () => {
    expect(cn("p-2", "text-sm")).toBe("p-2 text-sm");
  });

  it("merges conflicting classes passed via arrays", () => {
    expect(cn(["bg-red-500"], ["bg-blue-500"])).toBe("bg-blue-500");
  });
});
