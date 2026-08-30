import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./fixtures";

test.describe("Exports", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("creating a Text Only export job shows up in the Recent Jobs table", async ({ page }) => {
    await page.goto("/exports");

    await page.getByTestId("export-card-text_only").getByRole("button", { name: "Create Export" }).click();

    // The new job is created with type "text_only" and status "pending"
    // (nothing valorizes it further yet, see PROGETTO.md § 7 Export TODOs) —
    // assert on the row appearing at all rather than a specific status,
    // since the real worker pipeline isn't implemented in this scaffold.
    const jobsTable = page.locator("table").last();
    await expect(jobsTable.getByText("Text Only").first()).toBeVisible({ timeout: 10_000 });
  });

  test("a Ready job exposes a working Download action", async ({ page }) => {
    await page.goto("/exports");

    // Depends on at least one job already being "ready" in this environment
    // (see docs/DATABASE.md § export retention / PROGETTO.md § 7: no real
    // worker marks jobs ready automatically today). Skip gracefully if none
    // exist yet, rather than asserting on state this suite doesn't control.
    const readyRow = page.locator("tr", { has: page.getByText("Ready", { exact: true }) }).first();
    const hasReadyJob = await readyRow.isVisible().catch(() => false);
    test.skip(!hasReadyJob, "No 'ready' export job exists in this environment yet.");

    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      readyRow.getByRole("button", { name: /download/i }).click(),
    ]);
    await popup.waitForLoadState();
    expect(popup.url()).not.toBe("about:blank");
  });
});
