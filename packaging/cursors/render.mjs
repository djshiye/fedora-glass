// Renders SVG files to transparent PNGs at given pixel sizes, with Chromium (the same
// engine Bibata's own build uses). Input: a JSON job file of
//   [{"svg": "<path>", "colors": [["#00FF00", "#fff"], ...], "out": {"<size>": "<png path>"}}]
// Run by build.py; not part of the app.
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');

const jobs = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 1 });
for (const job of jobs) {
    let svg = readFileSync(job.svg, 'utf8');
    for (const [from, to] of job.colors)
        svg = svg.replaceAll(new RegExp(from, 'gi'), to);
    for (const [size, out] of Object.entries(job.out)) {
        const s = Number(size);
        const sized = svg.replace(/<svg([^>]*?)\swidth="[^"]*"([^>]*?)\sheight="[^"]*"/,
                                  `<svg$1 width="${s}"$2 height="${s}"`);
        await page.setViewportSize({ width: s, height: s });
        await page.setContent(`<html><body style="margin:0;background:transparent">${sized}</body></html>`);
        const buf = await page.locator('svg').first().screenshot({ omitBackground: true });
        writeFileSync(out, buf);
    }
}
await browser.close();
