#!/usr/bin/env node
/**
 * Verifies mobile sports card layout using mock preview page only.
 * Does NOT call sports scan / odds APIs.
 */
import { chromium } from "playwright";

const BASE_URL = process.env.PREVIEW_URL ?? "http://127.0.0.1:3000";
const MIN_TITLE_WIDTH_RATIO = 0.7;
const VIEWPORT_WIDTH = 390;

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: VIEWPORT_WIDTH, height: 844 } });

  const url = `${BASE_URL}/dev/sports-card-preview`;
  const response = await page.goto(url, { waitUntil: "networkidle", timeout: 60_000 });
  if (!response?.ok()) {
    throw new Error(`Preview page failed to load (${response?.status() ?? "no response"}): ${url}`);
  }

  await page.waitForSelector('[data-testid="sports-card-preview"] h2', { timeout: 15_000 });

  const metrics = await page.evaluate(() => {
    const title = document.querySelector(".signal-card__title");
    const body = document.querySelector(".signal-card__body");
    const card = document.querySelector(".signal-card");
    if (!title || !body || !card) {
      return { error: "Missing signal card elements" };
    }

    const titleRect = title.getBoundingClientRect();
    const bodyRect = body.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const titleStyle = getComputedStyle(title);
    const lines = (title.textContent ?? "")
      .trim()
      .split(/\s+/)
      .map((word) => {
        const probe = document.createElement("span");
        probe.style.position = "absolute";
        probe.style.visibility = "hidden";
        probe.style.whiteSpace = "nowrap";
        probe.textContent = word;
        document.body.appendChild(probe);
        const onOwnLine = titleRect.width < probe.getBoundingClientRect().width * 1.15;
        probe.remove();
        return onOwnLine;
      });

    return {
      viewportWidth: window.innerWidth,
      cardWidth: cardRect.width,
      bodyWidth: bodyRect.width,
      titleWidth: titleRect.width,
      titleText: title.textContent?.trim() ?? "",
      singleWordLines: lines.filter(Boolean).length,
      whiteSpace: titleStyle.whiteSpace,
    };
  });

  await browser.close();

  if ("error" in metrics) {
    throw new Error(metrics.error);
  }

  const widthRatio = metrics.titleWidth / metrics.viewportWidth;
  const passed =
    metrics.titleWidth >= VIEWPORT_WIDTH * MIN_TITLE_WIDTH_RATIO &&
    metrics.singleWordLines <= 1;

  console.log(JSON.stringify({ passed, ...metrics, widthRatio }, null, 2));

  if (!passed) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
