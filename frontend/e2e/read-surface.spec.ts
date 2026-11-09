import { expect, test } from "@playwright/test";
import axe from "axe-core";

test("required read surfaces remain accessible and visually stable", async ({ page, request }) => {
  const marketPayload = await (await request.get("/api/v1/markets?page_size=10")).json();
  const familyPayload = await (await request.get("/api/v1/families?page_size=1")).json();
  const versionPayload = await (await request.get("/api/v1/versions")).json();
  const marketId = marketPayload.data.items[0].market_id;
  const familyId = familyPayload.data.items[0].family_id;
  const routes = [
    ["overview", "/", /see the market universe/i],
    ["universe", "/universe", /market universe/i],
    ["market-detail", `/markets/${marketId}`, /canonical market/i],
    ["families", "/families", /operating families/i],
    ["family-detail", `/families/${familyId}`, /boundary notice/i],
    ["batches", "/batches", /research batches/i],
    ["audit", "/audit", /versions and receipts/i],
  ] as const;

  for (const [name, route, readyText] of routes) {
    await test.step(name, async () => {
      await page.goto(route);
      await expect(page.getByText(readyText).first()).toBeVisible();
      if (name === "overview") {
        await expect(page.getByRole("heading", { name: "Canonical markets", exact: true })).toBeVisible();
        const rows = page.locator(".market-row");
        await expect(rows).toHaveCount(marketPayload.data.items.length);
        for (const row of await rows.all()) {
          expect(await row.locator(":scope > span").first().evaluate(element => {
            const content = element.getBoundingClientRect();
            const row = element.closest(".market-row")!.getBoundingClientRect();
            return content.left >= row.left - 1 && content.right <= row.right + 1;
          })).toBe(true);
          const status = row.locator(".status");
          await expect(status).toBeVisible();
          // Visibility alone does not detect clipped text inside a flex/grid child.
          expect(await status.evaluate(element => {
            const badge = element.getBoundingClientRect();
            const row = element.closest(".market-row")!.getBoundingClientRect();
            return badge.left >= row.left - 1 && badge.right <= row.right + 1
              && element.scrollWidth <= element.clientWidth + 1
              && element.scrollHeight <= element.clientHeight + 1;
          })).toBe(true);
        }
      }
      if (name === "overview") {
        const panel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Canonical markets", exact: true }) });
        await expect(panel).toHaveScreenshot("overview-markets.png");
      }
      if (name === "family-detail") {
        await expect(page.locator(".metric-grid.small .metric strong").nth(0)).toHaveText("80");
        await expect(page.locator(".metric-grid.small .metric strong").nth(2)).toHaveText("1");
      }
      await page.addScriptTag({ content: axe.source });
      const results = await page.evaluate(async () => {
        return await (window as typeof window & { axe: typeof axe }).axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] },
        });
      });
      expect(results.violations, results.violations.map(item => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
      await expect(page).toHaveScreenshot(`${name}.png`);
    });
  }

  await test.step("historical snapshot selection", async () => {
    const historical = versionPayload.data.compatible_snapshots.find(
      (item: { current: boolean }) => !item.current,
    );
    const key = `${historical.source_run_id}|${historical.partition_id}|${historical.graph_version_id}`;
    await page.goto("/");
    await page.getByRole("combobox", { name: /research snapshot/i }).selectOption(key);
    await expect(page).toHaveURL(new RegExp(`partition_id=${encodeURIComponent(historical.partition_id)}`));
    await expect(page.getByLabel("Current data version")).toContainText(historical.partition_id);
    await page.getByRole("link", { name: "Audit", exact: true }).click();
    const panel = page.locator("section.panel").filter({ has: page.getByRole("heading", { name: "Current provenance" }) });
    await expect(panel).toContainText(historical.partition_id);
    await expect(panel).not.toContainText(versionPayload.data.current.partition_id);
  });

  await test.step("partial version URLs fail closed and recover", async () => {
    await page.goto("/audit?partition_id=nonexistent");
    await expect(page.getByText("Unable to load this view.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Current provenance" })).toHaveCount(0);
    await page.getByRole("combobox", { name: /research snapshot/i }).selectOption("latest");
    await expect(page.getByRole("heading", { name: "Current provenance" })).toBeVisible();
  });
});


test("long synthetic market status stays readable in a narrow row", async ({ page }) => {
  // Presentation-only stress fixture; never represents accepted research state.
  await page.goto("/");
  const status = page.locator(".market-row .status").first();
  await expect(status).toBeVisible();
  await status.evaluate(element => {
    element.textContent = "synthetic_".repeat(30);
    element.closest<HTMLElement>(".market-row")!.style.width = "160px";
  });
  expect(await status.evaluate(element => {
    const badge = element.getBoundingClientRect();
    const row = element.closest(".market-row")!.getBoundingClientRect();
    return badge.left >= row.left - 1 && badge.right <= row.right + 1
      && element.scrollWidth <= element.clientWidth + 1;
  })).toBe(true);
});
