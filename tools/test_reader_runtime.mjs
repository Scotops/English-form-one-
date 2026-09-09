#!/usr/bin/env node
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const moduleRoots = [process.env.ADT_NODE_MODULES, process.env.NODE_PATH, process.cwd()].filter(Boolean);
const { chromium } = require(require.resolve("playwright", { paths: moduleRoots }));
const root = process.cwd();
const failures = [];
const checks = [];

function assert(condition, message) {
  checks.push(message);
  if (!condition) failures.push(message);
}

const mime = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
  ".mp3": "audio/mpeg", ".wav": "audio/wav", ".woff": "font/woff", ".woff2": "font/woff2",
};

const server = http.createServer((request, response) => {
  const url = new URL(request.url || "/", "http://127.0.0.1");
  const relative = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html";
  const candidate = path.resolve(root, relative);
  if (!candidate.startsWith(root + path.sep) && candidate !== path.join(root, "index.html")) {
    response.writeHead(403).end("Forbidden");
    return;
  }
  fs.readFile(candidate, (error, data) => {
    if (error) {
      response.writeHead(404).end("Not found");
      return;
    }
    response.writeHead(200, { "Content-Type": mime[path.extname(candidate).toLowerCase()] || "application/octet-stream" });
    response.end(data);
  });
});

await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;
const executablePath = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find(fs.existsSync);
const browser = await chromium.launch({ headless: true, executablePath });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const consoleErrors = [];
page.on("pageerror", error => consoleErrors.push(error.message));
page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });

async function open(file) {
  await page.goto(`${base}/${file}`, { waitUntil: "networkidle" });
  await page.waitForSelector("#content");
  await page.waitForFunction(() => getComputedStyle(document.querySelector("#content")).opacity !== "0");
}

try {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "content", "pages.json"), "utf8"));
  assert(manifest.length === 192, "reading order contains exactly 192 canonical PDF pages");
  assert(!manifest.some(entry => /qz\d+\.html/i.test(entry.href)), "reading order has no detached or duplicated quiz pages");

  await open("index.html");
  const firstCoverId = await page.locator("#content [data-id]").first().getAttribute("data-id");
  assert(firstCoverId === "pg001_cover_title", "cover narration starts with the word English");

  await open("pg003_sec001.html");
  const tocSpeech = await page.locator('[data-id="pg003_n0007"]').innerText();
  assert(/Page number Roman number five/i.test(tocSpeech), "table of contents says Roman page number five in the required order");
  const tocNarrated = await page.locator("#content [data-id]").allInnerTexts();
  assert(!tocNarrated.some(text => /front matter page|printed book page/i.test(text)), "table of contents omits reader-only page labels");

  await open("pg005_sec001.html");
  const editorCredit = await page.locator('[data-id="pg005_credit_editors"]').innerText();
  assert(/^Editors:/i.test(editorCredit) && /Emmanuel P\. Lema/.test(editorCredit), "acknowledgements include the complete Editors credit");

  await open("pg071_sec001.html");
  const questionText = await page.locator('[data-id="pg071_im003"]').innerText();
  assert(/What is the story about\?/.test(questionText) && /rainy day/.test(questionText), "question artwork is reconstructed as complete live HTML text");
  await page.getByRole("button", { name: /Activate text to speech/i }).click();
  await page.waitForSelector("#content [data-word-index]", { timeout: 8000 });
  await page.waitForSelector("#content [data-word-index].bg-yellow-300", { timeout: 8000 });
  const highlightedWord = page.locator("#content [data-word-index].bg-yellow-300").first();
  const background = await highlightedWord.evaluate(node => getComputedStyle(node).backgroundColor);
  assert(!/rgba?\(0, 0, 0(?:, 0)?\)/.test(background), "live read-aloud creates word spans and advances a visible yellow highlight");
  const questionAudio = await page.request.get(`${base}/content/i18n/en/audio/pg071_im003.wav`);
  const audioBytes = await questionAudio.body();
  assert(questionAudio.ok() && audioBytes.subarray(0, 4).toString("ascii") === "RIFF", "corrected question narration audio is a valid local WAV file");

  await open("pg058_sec001.html");
  assert((await page.locator(".adt-printed-page-number").innerText()).trim() === "52", "printed page number 52 remains visible");
  assert(await page.locator(".adt-printed-page-number").getAttribute("aria-hidden") === "true", "printed folio is not redundantly narrated");
  await page.locator(".adt-workspace-toggle").click();
  const optionCount = await page.locator("#adt-activity-select option").count();
  assert(optionCount >= 2, "interactive workspace detects both exercises on the page");
  await page.locator("#adt-activity-response").fill("Runtime persistence check");
  await page.locator("#adt-response-save").click();
  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".adt-workspace-toggle").click();
  assert(await page.locator("#adt-activity-response").inputValue() === "Runtime persistence check", "exercise response persists after reload");
  await page.locator("#adt-response-clear").click();
  assert(await page.locator("#adt-activity-response").inputValue() === "", "exercise response Clear control works");

  assert(consoleErrors.length === 0, `runtime produced no browser errors (observed ${consoleErrors.length})`);
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}

const result = { checks: checks.length, failures, passed: failures.length === 0 };
console.log(JSON.stringify(result, null, 2));
if (failures.length) process.exitCode = 1;
