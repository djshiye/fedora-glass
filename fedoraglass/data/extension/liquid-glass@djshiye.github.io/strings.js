// Made by packaging/translations.py from fedoraglass/data/po/*.po: do not edit by hand.
// The extension's words in the languages the app speaks; English when there is none.

import GLib from 'gi://GLib';

const WORDS = {
    "de": {
        "Everything is set in the Fedora Glass app, with a live preview.": "Alles wird in der Fedora-Glass-App eingestellt, mit Live-Vorschau.",
        "Glass": "Glas",
        "Good afternoon": "Guten Tag",
        "Good evening": "Guten Abend",
        "Good morning": "Guten Morgen",
        "Good night": "Gute Nacht",
        "Open": "Öffnen",
        "Open Fedora Glass": "Fedora Glass öffnen",
        "Paused": "Pausiert",
        "Safe mode": "Abgesicherter Modus",
        "The Fedora Glass app is not installed.": "Die Fedora-Glass-App ist nicht installiert."
    },
    "es": {
        "Everything is set in the Fedora Glass app, with a live preview.": "Todo se configura en la aplicación Fedora Glass, con vista previa en vivo.",
        "Glass": "Cristal",
        "Good afternoon": "Buenas tardes",
        "Good evening": "Buenas noches",
        "Good morning": "Buenos días",
        "Good night": "Buenas noches",
        "Open": "Abrir",
        "Open Fedora Glass": "Abrir Fedora Glass",
        "Paused": "En pausa",
        "Safe mode": "Modo seguro",
        "The Fedora Glass app is not installed.": "La aplicación Fedora Glass no está instalada."
    },
    "fr": {
        "Everything is set in the Fedora Glass app, with a live preview.": "Tout se règle dans l’application Fedora Glass, avec un aperçu en direct.",
        "Glass": "Verre",
        "Good afternoon": "Bon après-midi",
        "Good evening": "Bonsoir",
        "Good morning": "Bonjour",
        "Good night": "Bonne nuit",
        "Open": "Ouverture",
        "Open Fedora Glass": "Ouvrir Fedora Glass",
        "Paused": "En pause",
        "Safe mode": "Mode sans échec",
        "The Fedora Glass app is not installed.": "L’application Fedora Glass n’est pas installée."
    },
    "it": {
        "Everything is set in the Fedora Glass app, with a live preview.": "Tutto si imposta nell'app Fedora Glass, con un'anteprima dal vivo.",
        "Glass": "Vetro",
        "Good afternoon": "Buon pomeriggio",
        "Good evening": "Buonasera",
        "Good morning": "Buongiorno",
        "Good night": "Buonanotte",
        "Open": "Apertura",
        "Open Fedora Glass": "Apri Fedora Glass",
        "Paused": "In pausa",
        "Safe mode": "Modalità sicura",
        "The Fedora Glass app is not installed.": "L'app Fedora Glass non è installata."
    },
    "pt_BR": {
        "Everything is set in the Fedora Glass app, with a live preview.": "Tudo é configurado no app Fedora Glass, com prévia ao vivo.",
        "Glass": "Vidro",
        "Good afternoon": "Boa tarde",
        "Good evening": "Boa noite",
        "Good morning": "Bom dia",
        "Good night": "Boa noite",
        "Open": "Abrir",
        "Open Fedora Glass": "Abrir o Fedora Glass",
        "Paused": "Pausado",
        "Safe mode": "Modo seguro",
        "The Fedora Glass app is not installed.": "O app Fedora Glass não está instalado."
    }
};

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
