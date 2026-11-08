// Quick Settings places a toggle's own menu (Wired, Wi-Fi) by an offset GNOME measures
// through the transforms between its grid and the box pointer. 1.5.1 measured it while
// the menu was still growing open (scaled), so the menus opened low and off to the side.
import assert from 'node:assert/strict';
import {test} from 'node:test';

globalThis.fake = {timeouts: {add: () => 1, remove: () => {}}, ui: null, Actor: class {}, Widget: class {}};
const Clutter = (await import('gi://Clutter')).default;
const {placeToggleMenus} = await import('../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/popups.js');

function menu(at) {
    const bp = {name: 'boxpointer'};
    const x = new Clutter.BindConstraint({coordinate: Clutter.BindCoordinate.X, source: bp, offset: 24.5});
    const y = new Clutter.BindConstraint({coordinate: Clutter.BindCoordinate.Y, source: bp, offset: 73.5});
    const w = new Clutter.BindConstraint({coordinate: Clutter.BindCoordinate.WIDTH, source: {}, offset: 0});
    return {
        _boxPointer: bp,
        _grid: {apply_relative_transform_to_point: (to, _p) => (to === bp ? at : null)},
        _overlay: {get_constraints: () => [x, y, w]},
        x, y, w,
    };
}

test('the offset is measured again at full size', () => {
    const m = menu({x: 19, y: 19, z: 0});
    assert.equal(placeToggleMenus(m), true);
    assert.equal(m.x.offset, 19);
    assert.equal(m.y.offset, 19);
    assert.equal(m.w.offset, 0, 'other constraints are left alone');
});

test('a GNOME without these parts is left alone', () => {
    assert.equal(placeToggleMenus({}), false);
    assert.equal(placeToggleMenus(null), false);
});
