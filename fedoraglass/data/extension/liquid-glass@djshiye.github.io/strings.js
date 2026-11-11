// Made by packaging/translations.py from fedoraglass/data/po/*.po: do not edit by hand.
// The extension's words in the languages the app speaks; English when there is none.

import GLib from 'gi://GLib';

const WORDS = {};

function pick() {
    for (const name of GLib.get_language_names?.() ?? []) {
        const code = name.split('.')[0].split('@')[0];
        if (code === 'C' || code === 'POSIX' || code.startsWith('en'))
            return null;
        if (WORDS[code])
            return WORDS[code];
        const base = code.split('_')[0];
        if (WORDS[base])
            return WORDS[base];
        if (base === 'pt' && WORDS.pt_BR)
            return WORDS.pt_BR;
    }
    return null;
}

let words;

/** The word in the session's language, or the English it was given. */
export function _(text) {
    words ??= pick() ?? {};
    return words[text] ?? text;
}
