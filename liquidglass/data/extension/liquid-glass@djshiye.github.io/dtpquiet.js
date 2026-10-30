// Wraps a Dash to Panel IconAnimator so the icons it wiggles can be told to
// skip updates that change nothing (see panels.js). Kept free of GNOME imports
// so tests/js/dtpquiet.test.js can check the wrap and undo with plain gjs.

const METHODS = ['addAnimation', 'removeAnimation'];

/**
 * quiet(target) / unquiet(target) are called as Dash to Panel starts and stops
 * wiggling an icon; warn(msg) is told when an undo has to leave a method alone.
 * Returns how to undo the wrap, or null if this animator isn't one we know.
 */
export function wrapAnimator(anim, quiet, unquiet, warn = () => {}) {
    const dancers = () => anim._animations?.dance ?? [];
    if (METHODS.some(m => typeof anim[m] !== 'function') || !Array.isArray(dancers()))
        return null;
    const dancing = target => dancers().some(p => p.target === target);
    const saved = {};
    const wrappers = {};
    for (const m of METHODS) {
        // Dash to Panel's own method, or one another extension put there first.
        saved[m] = {own: Object.hasOwn(anim, m), fn: anim[m]};
    }
    wrappers.addAnimation = function (target, name) {
        saved.addAnimation.fn.call(this, target, name);
        if (name === 'dance' && dancing(target))
            quiet(target);
    };
    wrappers.removeAnimation = function (target, name) {
        saved.removeAnimation.fn.call(this, target, name);
        if (name === 'dance' && !dancing(target))
            unquiet(target);
    };
    for (const m of METHODS)
        anim[m] = wrappers[m];
    dancers().forEach(p => quiet(p.target));

    return () => {
        dancers().forEach(p => unquiet(p.target));
        for (const m of METHODS) {
            if (anim[m] !== wrappers[m]) {
                // Someone wrapped on top of ours: taking ours out would drop theirs.
                // Ours stays under theirs and still calls the original.
                warn(`Dash to Panel's ${m} was wrapped again after Liquid Glass; leaving it as it is`);
                continue;
            }
            if (saved[m].own)
                anim[m] = saved[m].fn;
            else
                delete anim[m];
        }
    };
}
