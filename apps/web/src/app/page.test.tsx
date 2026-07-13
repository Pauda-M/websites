import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "@/app/page";

describe("Home (landing page)", () => {
  it("renders the hero heading", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Consulting and software, engineered for outcomes.",
      }),
    ).toBeInTheDocument();
  });

  it("renders the PB Solutions wordmark in the header", () => {
    render(<Home />);
    const header = screen.getByRole("banner");
    expect(header).toHaveTextContent("PB Solutions");
  });

  it("renders the main navigation links", () => {
    render(<Home />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveTextContent("Services");
    expect(nav).toHaveTextContent("Platform");
    expect(nav).toHaveTextContent("Status");
  });

  it("renders all four service cards", () => {
    render(<Home />);
    for (const title of [
      "Consulting",
      "CRM & Client Portal",
      "AI Services",
      "Support & Ticketing",
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });

  it("renders the platform section", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 2, name: "The PB Platform" })).toBeInTheDocument();
  });

  it("renders the footer copyright", () => {
    render(<Home />);
    expect(screen.getByText(/© 2026 PB Solutions/)).toBeInTheDocument();
  });
});
