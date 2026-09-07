import { test, expect, type Page } from "@playwright/test";

const admin = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "admin@example.test",
  name: "Admin",
  role: "admin",
  mfa_enabled: true,
  status: "active",
};

const enabledSource = {
  id: "10000000-0000-4000-8000-000000000001",
  code: "original",
  name: "Original source",
  country: "N/D",
  status: "healthy",
  enabled: true,
  priority: "high",
  lastRunAt: null,
  itemsLast24h: 0,
  errorRate: 0,
  consecutiveFailures: 0,
  hasScrapeConfig: true,
};

const disabledSource = {
  ...enabledSource,
  id: "20000000-0000-4000-8000-000000000002",
  code: "disabled_source",
  name: "Disabled source",
  status: "offline",
  enabled: false,
};

async function mockSourcesPage(page: Page, role = "admin", extraSources: typeof enabledSource[] = []) {
  await page.addInitScript(() => {
    localStorage.setItem("lavoro_esterno_access_token", "token");
    localStorage.setItem("lavoro_esterno_refresh_token", "refresh");
  });
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: { ...admin, role } }),
  );
  await page.route("**/api/v1/notifications", (route) =>
    route.fulfill({ json: { items: [], unreadCount: 0 } }),
  );
  await page.route("**/api/v1/sources/summary", (route) =>
    route.fulfill({ json: { total: 2 + extraSources.length, active: 1, degraded: 0, offline: 1 } }),
  );
  await page.route("**/api/v1/sources", (route) =>
    route.fulfill({ json: [enabledSource, disabledSource, ...extraSources] }),
  );
}

test("admin duplicates a source with a collision-safe suggested identity", async ({ page }) => {
  await mockSourcesPage(page, "admin", [{
    ...enabledSource,
    id: "40000000-0000-4000-8000-000000000004",
    code: "original_copy",
    name: "Existing copy",
  }]);
  let requestBody: unknown;
  await page.route(`**/api/v1/sources/${enabledSource.id}/duplicate`, async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      json: {
        ...enabledSource,
        id: "30000000-0000-4000-8000-000000000003",
        code: "original_copy_2",
        name: "Original source (copy)",
        status: "offline",
        enabled: false,
      },
    });
  });

  await page.goto("/sources");
  const originalRow = page.getByRole("row").filter({ hasText: "Original source" });
  await originalRow.hover();
  await originalRow.getByRole("button", { name: "Duplicate Original source" }).click();

  const dialog = page.getByRole("dialog", { name: "Duplicate source" });
  await expect(dialog.getByLabel("Name")).toHaveValue("Original source (copy)");
  await expect(dialog.getByLabel("Slug (unique identifier)")).toHaveValue("original_copy_2");
  await dialog.getByRole("button", { name: "Duplicate", exact: true }).click();

  await expect(dialog).toBeHidden();
  expect(requestBody).toEqual({ name: "Original source (copy)", slug: "original_copy_2" });
});

test("disabled source exposes Enable and hides operational stop actions", async ({ page }) => {
  await mockSourcesPage(page);
  let enabled = false;
  await page.route(`**/api/v1/sources/${disabledSource.id}/enable`, async (route) => {
    enabled = true;
    await route.fulfill({ status: 204 });
  });

  await page.goto("/sources");
  const disabledRow = page.getByRole("row").filter({ hasText: "Disabled source" });
  await disabledRow.hover();
  await expect(disabledRow.getByRole("button", { name: "Enable Disabled source" })).toBeVisible();
  await expect(disabledRow.getByTitle("Pause")).toHaveCount(0);
  await expect(disabledRow.getByTitle("Disable")).toHaveCount(0);
  await expect(disabledRow.getByTitle("Run Scan")).toHaveCount(0);
  await disabledRow.getByRole("button", { name: "Enable Disabled source" }).click();
  await expect.poll(() => enabled).toBe(true);
});

test("duplicate action is hidden from operators", async ({ page }) => {
  await mockSourcesPage(page, "operator");
  await page.goto("/sources");
  await expect(page.getByRole("button", { name: /Duplicate / })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Enable Disabled source" })).toBeAttached();
});

test("slug collision keeps the duplicate dialog open and shows the API error", async ({ page }) => {
  await mockSourcesPage(page);
  await page.route(`**/api/v1/sources/${enabledSource.id}/duplicate`, (route) =>
    route.fulfill({ status: 409, json: { detail: "Una fonte con slug 'original_copy' esiste gia." } }),
  );

  await page.goto("/sources");
  await page.getByRole("row").filter({ hasText: "Original source" }).hover();
  await page.getByRole("button", { name: "Duplicate Original source" }).click();
  const dialog = page.getByRole("dialog", { name: "Duplicate source" });
  await dialog.getByRole("button", { name: "Duplicate", exact: true }).click();

  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Una fonte con slug 'original_copy' esiste gia.")).toBeVisible();
});

test("enable failure is surfaced without hiding the source", async ({ page }) => {
  await mockSourcesPage(page);
  await page.route(`**/api/v1/sources/${disabledSource.id}/enable`, (route) =>
    route.fulfill({ status: 503, json: { detail: "Riabilitazione temporaneamente non disponibile." } }),
  );

  await page.goto("/sources");
  await page.getByRole("row").filter({ hasText: "Disabled source" }).hover();
  await page.getByRole("button", { name: "Enable Disabled source" }).click();

  await expect(page.getByRole("alert")).toContainText("Something went wrong on the server.");
  await expect(page.getByText("Disabled source")).toBeVisible();
});
