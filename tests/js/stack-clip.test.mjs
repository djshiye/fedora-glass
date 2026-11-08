// Notifications stacked in the calendar: the cards behind the see-through front card
// are cut to the strip that peeks out under it (stackclip.js).
import assert from 'node:assert/strict';
import {test} from 'node:test';

class Actor {
    connect() { return 1; }
    disconnect() {}
}
// A stand-in for GNOME's group, with the one method stackclip wraps.
class NotificationMessageGroup {
    _updateStackedMessagesFade() { this.faded = (this.faded ?? 0) + 1; }
}
globalThis.fake = {Actor, ui: new Actor(), overview: {visible: false}, NotificationMessageGroup,
    layoutManager: {uiGroup: {get_children: () => []}}};
globalThis.global = {window_group: {}};

const {peek, stackOf, StackClip} = await import(
    '../../fedoraglass/data/extension/liquid-glass@djshiye.github.io/stackclip.js');

test('a card behind keeps only the strip under the front card', () => {
    // Front card 0..109, the card behind 7..117 (GNOME lays it a few px lower).
    assert.deepEqual(peek({y1: 7, y2: 117}, {y1: 0, y2: 109}, 327), [0, 102, 327, 8]);
});

test('a card wholly behind the front card is cut away, one below it is whole', () => {
    assert.deepEqual(peek({y1: 0, y2: 100}, {y1: 0, y2: 109}, 300), [0, 100, 300, 0]);
    assert.deepEqual(peek({y1: 120, y2: 220}, {y1: 0, y2: 109}, 300), [0, 0, 300, 100]);
    assert.equal(peek({y1: 0, y2: 0}, {y1: 0, y2: 109}, 300), null);
});

test('GNOME keeps a group as front, cover, the stack, then the header', () => {
    const kids = ['front', 'cover', 'a', 'b', 'header'];
    assert.deepEqual(stackOf({get_children: () => kids}), {front: 'front', stack: ['a', 'b']});
    assert.deepEqual(stackOf({get_children: () => ['cover', 'header']}), {front: null, stack: []});
});

test('turning the glass off puts GNOME\'s own method back', () => {
    const own = NotificationMessageGroup.prototype._updateStackedMessagesFade;
    const s = new StackClip({});
    assert.notEqual(NotificationMessageGroup.prototype._updateStackedMessagesFade, own);
    const g = new NotificationMessageGroup();
    g.get_children = () => [];
    g._updateStackedMessagesFade();
    assert.equal(g.faded, 1, 'GNOME\'s own work still runs');
    s.destroy();
    assert.equal(NotificationMessageGroup.prototype._updateStackedMessagesFade, own);
});
