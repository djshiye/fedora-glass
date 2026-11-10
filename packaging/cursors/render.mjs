// Renders SVG files to transparent PNGs at given pixel sizes, with Chromium (the same
// engine Bibata's own build uses). Input: a JSON job file of
//   [{"svg": "<path>", "colors": [["#00FF00", "#fff"], ...], "out": {"<size>": "<png path>"},
//     "hide": ["#hotspot"],                 // optional: elements not to draw
//     "rotate": {"sel": "#spinner", "deg": 30},  // optional: turn one part (busy frames)
//     "probe": "#hotspot"}]                 // optional: report where this element is
// Probes are written to the second argument as JSON: {"<job index>": [x, y]}, the top left
// of the element in the SVG's own units. Run by build.py; not part of the app.
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');

const jobs = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const probes = {};
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 1 });

function sizedSvg(svg, s) {
    // Set width and height on the root element, whatever order or form they come in.
    return svg.replace(/<svg\b([^>]*)>/, (m, attrs) => {
        // Without a viewBox the drawing would not scale with the new size.
        if (!/\sviewBox=/.test(attrs)) {
            const w = /\swidth="([\d.]+)(px)?"/.exec(attrs), h = /\sheight="([\d.]+)(px)?"/.exec(attrs);
            if (w && h) attrs += ` viewBox="0 0 ${w[1]} ${h[1]}"`;
        }
        attrs = attrs.replace(/\s(width|height)="[^"]*"/g, '');
        return `<svg${attrs} width="${s}" height="${s}">`;
    });
}

for (const [index, job] of jobs.entries()) {
    let svg = readFileSync(job.svg, 'utf8');
    for (const [from, to] of job.colors || [])
        svg = svg.replaceAll(new RegExp(from, 'gi'), to);
    const prep = async () => {
        await page.evaluate(({ hide, rotate }) => {
            const root = document.querySelector('svg');
            for (const sel of hide || [])
                for (const el of root.querySelectorAll(sel)) el.setAttribute('display', 'none');
            if (rotate) {
                const el = root.querySelector(rotate.sel);
                const b = el.getBBox();
                const old = el.getAttribute('transform') || '';
                el.setAttribute('transform',
                    `${old} rotate(${rotate.deg} ${b.x + b.width / 2} ${b.y + b.height / 2})`.trim());
            }
        }, { hide: job.hide, rotate: job.rotate });
    };
    if (job.probe) {
        await page.setViewportSize({ width: 512, height: 512 });
        await page.setContent(`<html><body style="margin:0">${svg}</body></html>`);
        probes[index] = await page.evaluate((sel) => {
            const root = document.querySelector('svg');
            const el = root.querySelector(sel);
            if (!el) return null;
            el.removeAttribute('display');
            el.style.display = 'inline';
            const vb = root.viewBox.baseVal;
            const r = root.getBoundingClientRect();
            const e = el.getBoundingClientRect();
            const kx = (vb && vb.width ? vb.width : r.width) / r.width;
            const ky = (vb && vb.height ? vb.height : r.height) / r.height;
            return [(e.left - r.left) * kx, (e.top - r.top) * ky];
        }, job.probe);
    }
    for (const [size, out] of Object.entries(job.out || {})) {
        const s = Number(size);
        await page.setViewportSize({ width: s, height: s });
        await page.setContent(`<html><body style="margin:0;background:transparent">${sizedSvg(svg, s)}</body></html>`);
        await prep();
        const buf = await page.locator('svg').first().screenshot({ omitBackground: true });
        writeFileSync(out, buf);
    }
}
if (process.argv[3]) writeFileSync(process.argv[3], JSON.stringify(probes));
await browser.close();
