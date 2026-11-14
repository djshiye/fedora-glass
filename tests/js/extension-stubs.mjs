// Loader hooks for extension.test.mjs: extension.js's own modules become stubs that the
// test fills in through globalThis.fakeMods, so only extension.js itself runs.
const EXPORTS = {
    'animations.js': ['Animations'], 'arcrescue.js': ['ArcMenuRescue'], 'config.js': ['Config'],
    'desktop.js': ['DesktopBehaviour'], 'frost.js': ['WeatherFrost'], 'lock.js': ['LockGlass'], 'lockwidgets.js': ['LockWidgets'],
    'popupstyle.js': ['PopupStyle'], 'paused.js': ['PausedStyle'], 'pausestate.js': ['PauseState'], 'safety.js': ['Safety', 'guarded'], 'speed.js': ['Speed'],
    'surfaces.js': ['GlassManager'], 'quicktoggle.js': ['GlassSwitch'], 'themetidy.js': ['UserThemesTidy'], 'tuning.js': ['effectiveConfig'],
    'Extension': ['Extension'],
};

export async function resolve(specifier, context, next) {
    if (specifier === 'resource:///org/gnome/shell/extensions/extension.js')
        return {url: 'stubmod:Extension', shortCircuit: true};
    if (context.parentURL?.endsWith('/liquid-glass@djshiye.github.io/extension.js') && specifier.startsWith('./'))
        return {url: `stubmod:${specifier.slice(2)}`, shortCircuit: true};
    return next(specifier, context);
}

export async function load(url, context, next) {
    if (url.startsWith('stubmod:')) {
        const name = url.slice(8);
        if (!(name in EXPORTS))
            throw new Error(`no stub for ${name}`);
        // GNOME's Extension is a base class; the rest are called with or without new, and a
        // plain function that returns an object works for both.
        const source = name === 'Extension' ? 'export class Extension {}' : EXPORTS[name]
            .map(n => `export const ${n} = function (...a) { return globalThis.fakeMods['${name}'].${n}(...a); };`)
            .join('\n');
        return {format: 'module', source, shortCircuit: true};
    }
    return next(url, context);
}
