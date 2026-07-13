import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("renders a button with its text content", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  it("applies default variant and size classes", () => {
    render(<Button>Default</Button>);
    const button = screen.getByRole("button", { name: "Default" });
    expect(button).toHaveClass("bg-primary", "text-primary-foreground", "h-9");
  });

  it("applies outline variant classes", () => {
    render(<Button variant="outline">Outline</Button>);
    const button = screen.getByRole("button", { name: "Outline" });
    expect(button).toHaveClass("border", "bg-background");
    expect(button).not.toHaveClass("bg-primary");
  });

  it("applies destructive variant classes", () => {
    render(<Button variant="destructive">Delete</Button>);
    expect(screen.getByRole("button", { name: "Delete" })).toHaveClass("bg-destructive");
  });

  it("applies size classes", () => {
    render(<Button size="lg">Large</Button>);
    expect(screen.getByRole("button", { name: "Large" })).toHaveClass("h-10");
  });

  it("merges custom className with variant classes", () => {
    render(<Button className="custom-class">Custom</Button>);
    const button = screen.getByRole("button", { name: "Custom" });
    expect(button).toHaveClass("custom-class", "bg-primary");
  });

  it("calls the onClick handler when clicked", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Press</Button>);

    await user.click(screen.getByRole("button", { name: "Press" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not call onClick when disabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        Disabled
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Disabled" });
    expect(button).toBeDisabled();
    await user.click(button).catch(() => {
      // pointer-events: none makes user-event throw; the assertion below is what matters
    });

    expect(onClick).not.toHaveBeenCalled();
  });

  it("renders the child element when asChild is set", () => {
    render(
      <Button asChild>
        <a href="/status">Status link</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Status link" });
    expect(link).toHaveAttribute("href", "/status");
    expect(link).toHaveClass("bg-primary");
  });
});
