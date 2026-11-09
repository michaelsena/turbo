import { expect, test } from "@playwright/test";
import axe from "axe-core";

test("required read surfaces remain accessible and visually stable", async ({ page, request }) => {
  const marketPayload = await (await request.get("/api/v1/markets?page_size=1")).json();
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
  });
});
