import { test, expect } from "@playwright/test";

const user = { id: "00000000-0000-4000-8000-000000000001", email: "admin@example.test", name: "Admin", role: "admin", mfa_enabled: true, status: "active" };

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("lavoro_esterno_access_token", "token");
    localStorage.setItem("lavoro_esterno_refresh_token", "refresh");
  });
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/notifications", (route) => route.fulfill({ json: { items: [], unreadCount: 0 } }));
});

test("records lists all sources without an explicit filter", async ({ page }) => {
  await page.route("**/api/v1/sources", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/records/search?*", (route) => route.fulfill({ json: { results: [], total: 0, page: 1, pageSize: 25 } }));
  await page.goto("/records");
  await expect(page.getByRole("heading", { name: "Records" })).toBeVisible();
  await expect(page.getByLabel("Source Origin")).toHaveValue("");
  await expect(page.getByText("No records match these filters.")).toBeVisible();
});

test("missing AI summary is an empty state rather than a query error", async ({ page }) => {
  const id = "639fd3fb-27d6-4389-9893-4b03b5b95e33";
  await page.route(`**/api/v1/records/${id}`, (route) => route.fulfill({ json: { id, phone: "***", phoneVisibility: "masked", canonicalTitle: "Test", canonicalDescription: "", confidenceScore: 1, sourcesCount: 1, occurrencesCount: 1, firstSeenAt: "2026-01-01T00:00:00Z", lastSeenAt: "2026-01-01T00:00:00Z", status: "verified", tags: [] } }));
  await page.route(`**/api/v1/records/${id}/ai-summary`, (route) => route.fulfill({ status: 204 }));
  await page.route(`**/api/v1/records/${id}/ai-summary/versions`, (route) => route.fulfill({ json: [] }));
  await page.goto(`/records/${id}/ai-summary`);
  await expect(page.getByText("No AI summary available for this record.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Generate Summary/ })).toBeVisible();
});

test("account button opens the account page", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
  await expect(page.getByText("admin@example.test")).toBeVisible();
});
