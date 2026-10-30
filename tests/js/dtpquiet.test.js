// gjs -m tests/js/dtpquiet.test.js : checks the Dash to Panel animator wrap and its undo.
import {wrapAnimator} from '../../liquidglass/data/extension/liquid-glass@djshiye.github.io/dtpquiet.js';

let failed = 0;
function check(ok, what) {
    if (!ok) {
        failed++;
        print(`FAIL ${what}`);
    }
}

// Shaped like Dash to Panel's IconAnimator: methods on the prototype.
class ProtoAnimator {
    constructor() {
        this._animations = {dance: []};
    }

    addAnimation(target, name) {
        this._animations[name].push({target});
    }

    removeAnimation(target, name) {
        this._animations[name] = this._animations[name].filter(p => p.target !== target);
    }
}

// The same, with the methods bound in the constructor (own properties).
class OwnAnimator {
    constructor() {
        this._animations = {dance: []};
        this.addAnimation = (target, name) => this._animations[name].push({target});
        this.removeAnimation = (target, name) => {
            this._animations[name] = this._animations[name].filter(p => p.target !== target);
        };
    }
}

function run(anim, label) {
    const quiet = new Set();
    const undo = wrapAnimator(anim, t => quiet.add(t), t => quiet.delete(t));
    check(typeof undo === 'function', `${label}: wraps`);
    const icon = {};
    anim.addAnimation(icon, 'dance');
    check(quiet.has(icon), `${label}: a wiggled icon is quieted`);
    anim.removeAnimation(icon, 'dance');
    check(!quiet.has(icon), `${label}: the wiggle ending unquiets it`);
    anim.addAnimation(icon, 'dance');
    return {quiet, undo, icon};
}

// Prototype methods: undo deletes ours and the prototype's show through.
{
    const anim = new ProtoAnimator();
    const {quiet, undo, icon} = run(anim, 'prototype');
    undo();
    check(!quiet.has(icon), 'prototype: undo unquiets every wiggled icon');
    check(!Object.hasOwn(anim, 'addAnimation') && !Object.hasOwn(anim, 'removeAnimation'),
        'prototype: undo leaves no own methods');
    anim.addAnimation({}, 'dance');
    check(anim._animations.dance.length === 2, 'prototype: Dash to Panel still works after undo');
}

// Own methods: undo puts the originals back instead of deleting them.
{
    const anim = new OwnAnimator();
    const orig = [anim.addAnimation, anim.removeAnimation];
    const {undo} = run(anim, 'own');
    undo();
    check(anim.addAnimation === orig[0] && anim.removeAnimation === orig[1], 'own: undo restores the originals');
    let threw = false;
    try {
        anim.addAnimation({}, 'dance');
    } catch {
        threw = true;
    }
    check(!threw && anim._animations.dance.length === 2, 'own: Dash to Panel still works after undo');
}

// Someone wraps on top of ours: undo leaves their wrapper (and ours under it) in place.
{
    const anim = new ProtoAnimator();
    const quiet = new Set();
    const warnings = [];
    const undo = wrapAnimator(anim, t => quiet.add(t), t => quiet.delete(t), m => warnings.push(m));
    let theirs = 0;
    const ours = anim.addAnimation;
    const top = function (target, name) {
        theirs++;
        return ours.call(this, target, name);
    };
    anim.addAnimation = top;
    undo();
    check(anim.addAnimation === top, 'stacked: their wrapper stays');
    check(!Object.hasOwn(anim, 'removeAnimation'), 'stacked: the method nobody else wrapped is undone');
    check(warnings.length === 1, `stacked: warns about the one it left (${warnings.length})`);
    anim.addAnimation({}, 'dance');
    check(theirs === 1 && anim._animations.dance.length === 1, 'stacked: their wrapper and Dash to Panel still run');
    check(quiet.size === 0, `stacked: ours left in the chain is inert after undo (${quiet.size} quieted)`);
}

// Not an animator we know: leave it alone.
check(wrapAnimator({}, () => {}, () => {}) === null, 'unknown shape: not wrapped');
check(wrapAnimator({addAnimation() {}, removeAnimation() {}, _animations: {}}, () => {}, () => {}) !== null,
    'no dancers yet: still wrapped');

if (failed) {
    print(`${failed} checks failed`);
    imports.system.exit(1);
}
print('all checks passed');
