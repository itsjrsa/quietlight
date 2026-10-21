import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import assert from "node:assert/strict";

// Always start isolated fixtures. Never accept a production URL or access key.
const fixture = spawn("python3", ["ui_fixture.py"], {
  stdio: ["ignore", "pipe", "inherit"],
});
const lines = createInterface({ input: fixture.stdout });
const configuration = await Promise.race([
  new Promise((resolve, reject) => {
    lines.once("line", (line) => {
      try {
        resolve(JSON.parse(line));
      } catch (error) {
        reject(error);
      }
    });
    fixture.once("error", reject);
    fixture.once("exit", () =>
      reject(new Error("Fixture exited before startup")),
    );
  }),
  new Promise((_, reject) =>
    setTimeout(
      () => reject(new Error("Fixture startup timed out")),
      15000,
    ).unref(),
  ),
]).catch((error) => {
  fixture.kill();
  throw error;
});
const base = `http://127.0.0.1:${configuration.port}`;
let browser;
const errors = [];
await mkdir("test-results", { recursive: true });
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
    headless: true,
    chromiumSandbox: true,
  });
  for (const width of [1440, 390, 320]) {
    const context = await browser.newContext({
      viewport: { width, height: 900 },
      isMobile: width < 500,
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    const fits = async (label) =>
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${label} overflows at ${width}px`,
      );
    await page.goto(base);
    await page.locator(".topic-card").first().waitFor();
    await fits("Home");
    await page.screenshot({
      path: `test-results/home-${width}.png`,
      fullPage: true,
    });
    await page.getByRole("searchbox", { name: "Search topics" }).fill("SPACE");
    assert.equal(await page.locator(".topic-card").count(), 1);
    await page.reload();
    await page.locator(".topic-card").waitFor();
    assert.equal(await page.getByRole("searchbox").inputValue(), "SPACE");
    await page.getByRole("searchbox").fill("nothing matches");
    await page.getByRole("heading", { name: "No topics found." }).waitFor();
    await page.getByRole("button", { name: "Show all topics" }).click();
    await page.locator('[data-topic-filter="new"]').click();
    assert.equal(await page.locator(".topic-card").count(), 2);
    await page.locator('[data-topic-filter="weekly"]').click();
    assert.ok(
      await page.locator('.topic-see-all[href="/topics/space"]').isVisible(),
    );
    await page.locator('[data-topic-filter="all"]').click();
    await page.locator('.topic-see-all[href="/topics/default"]').click();
    await page
      .getByRole("heading", { name: "Your journal", exact: true })
      .waitFor();
    await page.locator(".featured-edition").click();
    await page.locator(".prose").waitFor();
    await fits("Article");
    assert.ok((await page.locator('.prose a[href^="http"]').count()) > 0);
    await page.screenshot({
      path: `test-results/article-${width}.png`,
      fullPage: true,
    });
    await page.goto(base + "/?filter=new");
    await page.locator(".topic-card").waitFor();
    assert.equal(await page.locator(".topic-card").count(), 1);
    assert.match(
      await page.locator(".topic-card").getAttribute("href"),
      /^\/topics\/space\/edition\//,
    );
    await page.reload();
    await page.locator(".topic-card").waitFor();
    assert.equal(await page.locator(".topic-card").count(), 1);
    await page.goto(base + "/topics/space");
    await page.locator(".featured-edition").click();
    await page
      .getByRole("heading", { name: "A view beyond Earth", exact: true })
      .waitFor();
    assert.match(page.url(), /\/topics\/space\/edition\//);
    await page.reload();
    await page
      .getByRole("heading", { name: "A view beyond Earth", exact: true })
      .waitFor();
    await page.locator(".back-link").click();
    await page
      .getByRole("heading", { name: "Space science", exact: true })
      .waitFor();
    await page.goto(base + "/settings");
    await page.locator(".key-help summary").click();
    await fits("Expanded key help");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Copy access key command" }).click();
    assert.equal(
      await page.evaluate(() => navigator.clipboard.readText()),
      "docker compose exec journal cat /data/journal/admin-token",
    );
    // Exercise the private-HTTP fallback where Clipboard API access is unavailable.
    await page.evaluate(() => {
      Object.defineProperty(navigator, "clipboard", {
        value: undefined,
        configurable: true,
      });
      document.execCommand = () => false;
    });
    await page.getByRole("button", { name: "Copy access key command" }).click();
    assert.equal(
      await page.evaluate(() => window.getSelection().toString()),
      "docker compose exec journal cat /data/journal/admin-token",
    );
    await page.locator("#access-key").fill(configuration.token);
    await page.locator('#unlock-form button[type="submit"]').click();
    await page.locator("#prompt").waitFor();
    await fits("Settings");
    assert.ok((await page.locator("#prompt").inputValue()).length > 10);
    await page.screenshot({
      path: `test-results/settings-${width}.png`,
      fullPage: true,
    });
    await page.locator("#save-settings").click();
    await page
      .getByText("Saved. Your next edition will follow this brief.")
      .waitFor();
    const originalBrief = await page.locator("#prompt").inputValue();
    await page.locator("#new-topic-name").fill(`Sports science ${width}`);
    await page.locator('#add-topic-form button[type="submit"]').click();
    await page.waitForURL(/\/settings\?topic=/);
    await page.waitForFunction(
      (name) => document.querySelector("#topic-name")?.value === name,
      `Sports science ${width}`,
    );
    assert.equal(
      await page.locator("#topic-name").inputValue(),
      `Sports science ${width}`,
    );
    assert.equal(await page.locator("#schedule-enabled").isChecked(), false);
    const topicId = new URL(page.url()).searchParams.get("topic");
    await page
      .locator("#prompt")
      .fill("Follow evidence about sports recovery and training.");
    await page.locator("#schedule-enabled").check();
    await page.locator("#schedule-enabled").check();
    await page.locator("#schedule-cadence").selectOption("weekly");
    await page.locator("#schedule-weekday").selectOption("3");
    await page.locator("#schedule-time").fill("10:30");
    await page.locator("#lookback-days").fill("7");
    await page.locator("#save-settings").click();
    await page
      .getByText("Saved. Your next edition will follow this brief.")
      .waitFor();
    await fits("Topic settings");
    await page.reload();
    await page.locator("#schedule-cadence").waitFor();
    assert.equal(
      await page.locator("#schedule-cadence").inputValue(),
      "weekly",
    );
    assert.equal(await page.locator("#schedule-weekday").inputValue(), "3");
    assert.equal(await page.locator("#schedule-time").inputValue(), "10:30");
    assert.equal(await page.locator("#lookback-days").inputValue(), "7");
    await page.screenshot({
      path: `test-results/weekly-settings-${width}.png`,
      fullPage: true,
    });
    await page.goto(base + `/topics/${topicId}`);
    await page.getByText("Every Wednesday at 10:30 · London").waitFor();
    await page.goto(base + `/settings?topic=${topicId}`);
    await page.locator("#schedule-enabled").waitFor();
    await page.locator("#schedule-enabled").uncheck();
    await page.locator("#save-settings").click();
    await page
      .getByText("Saved. Your next edition will follow this brief.")
      .waitFor();
    await page.reload();
    await page.locator("#schedule-enabled").waitFor();
    assert.equal(await page.locator("#schedule-enabled").isChecked(), false);
    await page.locator("#topic-select").selectOption("default");
    await page.waitForURL(/topic=default/);
    await page.waitForFunction(
      (brief) => document.querySelector("#prompt")?.value === brief,
      originalBrief,
    );
    assert.equal(await page.locator("#schedule-cadence").inputValue(), "daily");
    assert.equal(await page.locator("#schedule-weekday").isVisible(), false);
    assert.equal(await page.locator("#schedule-time").inputValue(), "08:00");
    await page.goto(base + `/topics/${topicId}`);
    await page
      .getByRole("heading", { name: `Sports science ${width}`, exact: true })
      .waitFor();
    await page.getByText("This topic is paused").waitFor();
    await fits("Empty topic");
    await page.reload();
    await page.getByText("Your next idea starts here.").waitFor();
    await page.goto(base);
    await page
      .getByRole("heading", { name: `Sports science ${width}`, exact: true })
      .waitFor();
    await fits("Topic collections");
    await page.locator(".topic-add").click();
    await page.locator("#lock-settings").waitFor();
    assert.equal(
      await page
        .locator("#new-topic-name")
        .evaluate((el) => document.activeElement === el),
      true,
    );
    await page.locator("#lock-settings").click();
    await page.locator("#access-key").waitFor();
    assert.equal(
      (await context.request.get(base + "/api/settings")).status(),
      401,
    );
    await context.close();
    console.log(
      `PASS ${width}px: journal, article, settings, save, logout, no horizontal overflow`,
    );
  }
  // Live research is topic-specific, safe to render, and refreshed while open.
  const progressPage = await browser.newPage({
    viewport: { width: 390, height: 844 },
  });
  let progressStage = "reading";
  let published = false;
  await progressPage.route("**/api/editions?topic=space", (route) =>
    route.fulfill({
      json: published
        ? [
            {
              id: "live-edition",
              date: "2026-10-21",
              title: "Fresh observations",
              summary: "Research completed.",
              minutes: 1,
              items: [],
            },
          ]
        : [],
    }),
  );
  await progressPage.route("**/api/status?topic=space", (route) =>
    route.fulfill({
      json: {
        online: true,
        busy: true,
        research: {
          active: true,
          events: [
            { stage: "searching", message: "Searching for new observations" },
            {
              stage: progressStage,
              message: "Observatory <script>alert(1)</script>",
              url: "https://example.org/observations",
            },
            {
              stage: "reading",
              message: "Unsafe link",
              url: "javascript:alert(1)",
            },
          ],
        },
      },
    }),
  );
  await progressPage.goto(base + "/topics/space");
  await progressPage.locator("#research-progress").waitFor();
  assert.equal(await progressPage.locator(".empty-state").isVisible(), false);
  assert.equal(await progressPage.locator("#research-progress a").count(), 1);
  assert.equal(
    await progressPage.locator("#research-progress script").count(),
    0,
  );
  assert.ok(
    await progressPage
      .locator("#research-progress")
      .innerText()
      .then((s) => s.includes("Reading")),
  );
  progressStage = "reviewed";
  await progressPage.waitForFunction(
    () =>
      document.querySelector(".research-events li:nth-child(2) > span")
        ?.textContent === "Read",
  );
  assert.ok(
    await progressPage.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  published = true;
  await progressPage
    .getByRole("heading", { name: "Fresh observations" })
    .waitFor();
  await progressPage.close();
  const sourcePage = await browser.newPage();
  sourcePage.on("pageerror", (error) => errors.push(error.message));
  await sourcePage.addInitScript(() => {
    localStorage.setItem(
      "fieldnotes.read-editions.v1",
      JSON.stringify({
        "legacy-topic": "previous-edition",
        invalid: 42,
      }),
    );
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (text) => {
          if (window.failClipboard) throw new Error("Clipboard unavailable");
          window.copiedSources = text;
        },
      },
    });
    document.execCommand = () => false;
  });
  await sourcePage.route("**/api/editions/2026-01-01?topic=default", (route) =>
    route.fulfill({
      json: {
        id: "citation-fixture",
        date: "2026-01-01",
        title: "Evidence worth sharing",
        minutes: 2,
        items: [
          {
            title: "Additional edition source",
            url: "https://example.org/extra",
          },
          {
            title: "Never expose credentials",
            url: ["https", "//user", "password@example.org"].join(":"),
          },
        ],
        markdown:
          '# Evidence worth sharing\n\n## A specific finding\n\nA supported claim [[1]](https://example.org/paper "Original paper — Example University, 2026-01-01"). Another claim [[1]](https://example.org/paper).\n\nA legacy [descriptive link](https://example.org/report "Report <script>unsafe</script>") remains readable.\n\n```text\n[99](https://example.org/not-a-source)\n```\n\n## Other sources consulted\n\n- [Background reading](https://example.org/background)\n',
      },
    }),
  );
  await sourcePage.goto(base + "/edition/2026-01-01");
  await sourcePage.locator(".edition-sources").waitFor();
  const migratedReads = await sourcePage.evaluate(() =>
    JSON.parse(localStorage.getItem("quietlight.read-editions.v1")),
  );
  assert.equal(migratedReads["legacy-topic"], "previous-edition");
  assert.equal(migratedReads.invalid, undefined);
  await sourcePage.locator("#copy-link").click();
  assert.equal(
    await sourcePage.locator("#copy-link").textContent(),
    "Link copied ✓",
  );
  assert.equal(
    await sourcePage.evaluate(() => window.copiedSources),
    sourcePage.url(),
  );
  assert.equal(
    await sourcePage.locator(".edition-sources").getAttribute("open"),
    null,
  );
  assert.equal(
    await sourcePage.locator(".edition-sources summary").textContent(),
    "Sources · 4Copy sources",
  );
  assert.deepEqual(
    await sourcePage.locator(".source-citation").allTextContents(),
    ["[1]", "[1]", "[2]"],
  );
  assert.equal(
    await sourcePage.locator(".source-citation").first().getAttribute("target"),
    null,
  );
  await sourcePage.locator(".source-citation").first().click();
  assert.notEqual(
    await sourcePage.locator(".edition-sources").getAttribute("open"),
    null,
  );
  assert.equal(
    await sourcePage.evaluate(() => document.activeElement.id),
    "source-1",
  );
  assert.equal(await sourcePage.locator(".edition-sources script").count(), 0);
  await sourcePage
    .getByRole("button", { name: "Copy sources", exact: true })
    .click();
  const copied = await sourcePage.evaluate(() => window.copiedSources);
  assert.match(
    copied,
    /Original paper — Example University, 2026-01-01\nhttps:\/\/example.org\/paper/,
  );
  assert.match(copied, /Other sources consulted/);
  assert.match(copied, /Other sources listed in this edition/);
  assert.ok(!copied.includes("password") && !copied.includes("not-a-source"));
  await sourcePage
    .getByRole("button", { name: "Copy source 2", exact: true })
    .click();
  assert.match(
    await sourcePage.evaluate(() => window.copiedSources),
    /^\[2\] descriptive link/,
  );
  await sourcePage.evaluate(() => {
    window.failClipboard = true;
  });
  await sourcePage
    .getByRole("button", { name: "Copy sources", exact: true })
    .click();
  assert.equal(
    await sourcePage.locator(".source-copy-fallback").inputValue(),
    copied,
  );
  await sourcePage.locator("#copy-link").click();
  assert.equal(
    await sourcePage.locator("#copy-link").textContent(),
    "Select link below",
  );
  assert.equal(
    await sourcePage.getByLabel("Edition link to copy").inputValue(),
    sourcePage.url(),
  );
  await sourcePage.evaluate(() => {
    document.execCommand = () => {
      window.copiedSources = document.activeElement.value;
      return true;
    };
  });
  await sourcePage.locator("#copy-link").click();
  assert.equal(
    await sourcePage.locator("#copy-link").textContent(),
    "Link copied ✓",
  );
  assert.equal(await sourcePage.locator(".link-copy-fallback").count(), 0);
  assert.equal(
    await sourcePage.evaluate(() => window.copiedSources),
    sourcePage.url(),
  );
  await sourcePage.evaluate(() => {
    localStorage.setItem(
      "quietlight.read-editions.v1",
      JSON.stringify({ "legacy-topic": "newer-edition" }),
    );
  });
  await sourcePage.reload();
  assert.equal(
    await sourcePage.evaluate(
      () =>
        JSON.parse(localStorage.getItem("quietlight.read-editions.v1"))[
          "legacy-topic"
        ],
    ),
    "newer-edition",
  );
  await sourcePage.locator(".edition-sources[open]").waitFor();
  for (const width of [1440, 390, 320]) {
    await sourcePage.setViewportSize({ width, height: 900 });
    assert.ok(
      await sourcePage.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await sourcePage.screenshot({
      path: `test-results/sources-${width}.png`,
      fullPage: true,
    });
  }
  await sourcePage.close();
  console.log(
    "PASS citations, deduplication, folded sources, copy fallback, deep links, and mobile layout",
  );
  // Isolated browser fixture: exercise diagram rendering and untrusted Markdown.
  const page = await browser.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/editions/2026-01-01?topic=default", (route) =>
    route.fulfill({
      json: {
        date: "2026-01-01",
        title: "Diagram test fixture",
        minutes: 1,
        items: [],
        markdown:
          '# Diagram test fixture\n\n## Method\n\n**A useful combination.**\n\n```mermaid\nflowchart LR\n A[Forecast A] --> C[Combine]\n B[Forecast B] --> C\n C --> D[Evaluate]\n```\n\n<script>window.compromised=true</script><img src=x onerror="window.compromised=true">\n\n[Bad link](javascript:alert(1))',
      },
    }),
  );
  await page.goto(base + "/edition/2026-01-01");
  await page.locator("figure.diagram svg").waitFor();
  assert.match(
    await page.locator("figure.diagram svg").textContent(),
    /Forecast A/,
  );
  assert.equal(await page.locator("figure.diagram foreignObject").count(), 0);
  assert.equal(await page.evaluate(() => !!window.compromised), false);
  assert.equal(await page.locator('.prose a[href^="javascript:"]').count(), 0);
  await page.screenshot({ path: "test-results/diagram.png", fullPage: true });
  await page.setViewportSize({ width: 320, height: 800 });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Diagram page overflows at 320px",
  );
  await page.screenshot({
    path: "test-results/diagram-mobile.png",
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  console.log(
    "PASS isolated diagram and untrusted-content fixture; no JavaScript errors",
  );
  await page.route("**/api/editions?topic=space", (route) =>
    route.fulfill({ status: 503, json: { error: "Archive unavailable" } }),
  );
  await page.goto(base);
  await page.getByText("The archive is temporarily unavailable.").waitFor();
  assert.ok(
    await page.locator('.topic-see-all[href="/topics/default"]').isVisible(),
  );
  console.log("PASS one unavailable archive does not hide other topics");
  await page.route("**/api/editions?topic=*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto(base);
  await page
    .getByText("Your first briefing will appear here.")
    .first()
    .waitFor();
  console.log("PASS empty journal onboarding");
  await page.route("**/api/topics", (route) =>
    route.fulfill({
      json: Array.from({ length: 20 }, (_, i) => ({
        id: "sample-" + i,
        name:
          i === 0
            ? '<img src=x onerror="window.compromised=true">'
            : "A".repeat(80) + i,
        enabled: true,
        schedule: {
          enabled: true,
          time: "08:00",
          cadence: i % 2 ? "weekly" : "daily",
          weekday: 1,
        },
      })),
    }),
  );
  await page.goto(base);
  await page.locator(".topic-card").last().waitFor();
  assert.equal(await page.locator(".topic-card").count(), 20);
  assert.equal(await page.locator(".topic-card img").count(), 0);
  assert.equal(await page.evaluate(() => !!window.compromised), false);
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await page.locator('[data-topic-filter="weekly"]').click();
  assert.equal(await page.locator(".topic-card").count(), 10);
  console.log(
    "PASS 20-topic library, long titles, escaped names, cadence filtering, and 320px layout",
  );
} finally {
  await browser?.close();
  lines.close();
  fixture.kill();
}
