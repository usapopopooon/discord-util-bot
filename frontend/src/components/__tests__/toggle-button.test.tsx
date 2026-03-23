import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToggleButton } from "../toggle-button";

const mockRefresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: mockRefresh,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

describe("ToggleButton", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockRefresh.mockClear();
    global.fetch = vi.fn().mockResolvedValue({ ok: true });
  });

  it("renders a switch element", () => {
    render(<ToggleButton endpoint="/api/test/1/toggle" enabled={false} />);
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  it("renders as checked when enabled is true", () => {
    render(<ToggleButton endpoint="/api/test/1/toggle" enabled={true} />);
    const switchEl = screen.getByRole("switch");
    expect(switchEl).toHaveAttribute("data-state", "checked");
  });

  it("renders as unchecked when enabled is false", () => {
    render(<ToggleButton endpoint="/api/test/1/toggle" enabled={false} />);
    const switchEl = screen.getByRole("switch");
    expect(switchEl).toHaveAttribute("data-state", "unchecked");
  });

  it("calls fetch with PATCH and toggled value on click", async () => {
    const user = userEvent.setup();
    render(<ToggleButton endpoint="/api/test/1/toggle" enabled={false} />);

    await user.click(screen.getByRole("switch"));

    expect(global.fetch).toHaveBeenCalledWith("/api/test/1/toggle", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });
  });

  it("sends enabled=false when currently enabled", async () => {
    const user = userEvent.setup();
    render(<ToggleButton endpoint="/api/test/1/toggle" enabled={true} />);

    await user.click(screen.getByRole("switch"));

    expect(global.fetch).toHaveBeenCalledWith("/api/test/1/toggle", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
  });

  it("calls router.refresh after toggle", async () => {
    const user = userEvent.setup();
    render(<ToggleButton endpoint="/api/test/1/toggle" enabled={false} />);

    await user.click(screen.getByRole("switch"));

    await waitFor(() => {
      expect(mockRefresh).toHaveBeenCalled();
    });
  });

  it("disables switch while loading", async () => {
    let resolvePromise!: () => void;
    global.fetch = vi.fn().mockReturnValue(
      new Promise<{ ok: boolean }>((resolve) => {
        resolvePromise = () => resolve({ ok: true });
      })
    );

    const user = userEvent.setup();
    render(<ToggleButton endpoint="/api/test/1/toggle" enabled={false} />);

    await user.click(screen.getByRole("switch"));

    expect(screen.getByRole("switch")).toBeDisabled();

    resolvePromise();
    await waitFor(() => {
      expect(mockRefresh).toHaveBeenCalled();
    });
  });
});
