import { expect, test } from "@playwright/test";

test("tema e risorse locali funzionano senza violazioni CSP", async ({ page }) => {
  const remoteFontRequests: string[] = [];
  const cspErrors: string[] = [];
  const localFonts: string[] = [];

  await page.addInitScript(() => localStorage.setItem("lavoro_esterno_theme", "dark"));
  page.on("request", (request) => {
    const url = request.url();
    if (/fonts\.(googleapis|gstatic)\.com/i.test(url)) remoteFontRequests.push(url);
    if (/\.woff2(?:\?|$)/i.test(url)) localFonts.push(url);
  });
  page.on("console", (message) => {
    if (/content security policy|violates.*csp/i.test(message.text())) cspErrors.push(message.text());
  });

  await page.goto("/login");
  const fontCounts = await page.evaluate(async () => {
    await document.fonts.ready;
    return [
      (await document.fonts.load("400 16px Inter", "Accesso")).length,
      (await document.fonts.load("400 16px 'JetBrains Mono'", "diagnostica")).length,
      (await document.fonts.load("400 24px 'Material Symbols Outlined'", "login")).length,
    ];
  });

  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator(".material-symbols-outlined").first()).toBeVisible();
  expect(fontCounts.every((count) => count > 0)).toBe(true);
  expect(remoteFontRequests).toEqual([]);
  expect(cspErrors).toEqual([]);
  expect(localFonts.length).toBeGreaterThan(0);
  expect(await page.locator("[style]").count()).toBe(0);
});
