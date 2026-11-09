import { expect, test } from "@playwright/test";
import axe from "axe-core";

test("required read surfaces remain accessible and visually stable", async ({ page, request }) => {
  const marketPayload = await (await request.get("/api/v1/markets?page_size=1")).json();
  const familyPayload = await (await request.get("/api/v1/families?page_size=1")).json();
  const versionPayload = await (await request.get("/api/v1/versions")).json();
  const marketId = marketPayload.data.items[0].market_id;
  const familyId = familyPayload.data.items[0].family_id;
  const marketDetail = (await (await request.get(`/api/v1/markets/${marketId}`)).json()).data;
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
      if (name === "market-detail") {
        await expect(page.getByRole("heading", { name: "Why this boundary exists", exact: true })).toBeVisible();
        const fields = ["buyer", "job_to_be_done", "delivery_model", "workforce_model", "economics_risk", "acquisition_universe", "ambient_ai_workflow"];
        const cards = page.locator(".market-identity-dimension");
        await expect(cards).toHaveCount(7);
        for (const [index, field] of fields.entries()) {
          await expect(cards.nth(index).locator(".market-identity-narrative")).toHaveText(marketDetail[field] || "Not recorded in this snapshot");
        }
        await expect(page.getByRole("heading", { name: "Explicit exclusions", exact: true })).toBeVisible();
        await expect(page.getByText(/it is not an investment score/i)).toBeVisible();
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
