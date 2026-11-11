// strings.js: the extension's few words in the session's language (GLib's language list),
// English for any language the app does not speak, and for C/POSIX.
import assert from 'node:assert/strict';
import {test} from 'node:test';

const DIR = new URL('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/', import.meta.url).href;
let n = 0;

async function wordsFor(languages) {
    globalThis.fake = {languages};
    // A fresh copy each time: the module picks its language once.
    const {_} = await import(`${DIR}strings.js?v=${n++}`);
    return {glass: _('Glass'), paused: _('Paused'), unknown: _('A word nobody marked')};
}

test('English when the session is C or English', async () => {
    assert.equal((await wordsFor(['C'])).glass, 'Glass');
    assert.equal((await wordsFor(['en_GB.UTF-8', 'en_GB', 'en', 'C'])).paused, 'Paused');
});

test('every language the app speaks has the tile words', async () => {
    for (const lang of ['de', 'es', 'fr', 'it', 'pt_BR']) {
        const w = await wordsFor([`${lang}.UTF-8`, lang, 'C']);
        assert.ok(w.glass && w.paused, lang);
        assert.notEqual(w.paused, 'Paused', `${lang} has a translation`);
        assert.equal(w.unknown, 'A word nobody marked');
    }
});

test('a country variant falls back to its language; Portuguese to Brazilian', async () => {
    const de = await wordsFor(['de']);
    assert.deepEqual(await wordsFor(['de_AT.UTF-8', 'de_AT', 'C']), de);
    const pt = await wordsFor(['pt_BR']);
    assert.deepEqual(await wordsFor(['pt_PT.UTF-8', 'pt_PT', 'pt', 'C']), pt);
});

test('a language we do not speak stays English', async () => {
    assert.equal((await wordsFor(['ja_JP.UTF-8', 'ja', 'C'])).paused, 'Paused');
});
