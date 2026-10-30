/* ---- geometry ---------------------------------------------------------- */
:root {
  --window-radius: $radius_window;
  --border-opacity: 12%;
}

/* ---- plain GTK 4 apps (no libadwaita) use fixed colours, so give them the same base ---- */
window.background { color: var(--window-fg-color); background-color: var(--window-bg-color); }
.view, iconview, textview > text { color: var(--view-fg-color); }
headerbar, .titlebar { color: var(--headerbar-fg-color); }
popover > contents { color: var(--popover-fg-color); }
tooltip.background { background-color: var(--lg-tooltip); }
entry, spinbutton, searchentry { color: var(--window-fg-color); }
label.dim-label, .dim-label { opacity: 0.55; }
treeview.view { background-color: var(--view-bg-color); }
treeview.view header button { background-color: transparent; border-radius: 0; box-shadow: none; background-image: none; }

/* ---- windows: deep soft shadow. The edge and its reflections are real glass,
   drawn by the Shell behind the window, so nothing here paints light. ---- */
window.csd {
  border-radius: $radius_window;
  outline: none;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.30),
    0 18px 48px 4px var(--lg-deep-shadow),
    0 4px 12px 0 var(--lg-shadow);
}
window.csd:backdrop {
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.22),
    0 8px 28px 2px var(--lg-shadow);
}
window.csd.maximized, window.csd.fullscreen, window.csd.tiled,
window.csd.tiled-top, window.csd.tiled-left, window.csd.tiled-right, window.csd.tiled-bottom {
  border-radius: 0;
  box-shadow: none;
}

/* ---- header bars: part of the window glass, hairline underneath ---------- */
headerbar {
  background-color: transparent;
  background-image: none;
  box-shadow: inset 0 -1px 0 var(--lg-divider);
  margin-left: 0;
  margin-right: 0;
  border-radius: 0;
}
headerbar:backdrop { background-color: transparent; }
headerbar.flat, toolbarview.flat > headerbar { box-shadow: none; }
/* One hairline under the top bar: a header bar inside it draws none of its own,
   or the two lines, a few px apart, read as stripes. */
.top-bar headerbar { box-shadow: none; }
.top-bar, tabbar .box { background-color: transparent; box-shadow: inset 0 -1px 0 var(--lg-divider); }
.titlebar { background-color: transparent; border-radius: 0; }
searchbar > revealer > box, actionbar > revealer > box {
  background-color: var(--lg-bar);
  box-shadow: inset 0 1px 0 var(--lg-divider);
}
searchbar > revealer > box { box-shadow: inset 0 -1px 0 var(--lg-divider); }

/* ---- sidebars (Nautilus, Settings-style split views) -------------------- */
.sidebar-pane, .navigation-sidebar-pane {
  background-color: var(--lg-chrome);
  box-shadow: inset -1px 0 0 var(--lg-divider);
}
.sidebar-pane:backdrop { background-color: var(--lg-chrome); }
.sidebar-pane:dir(rtl) { box-shadow: inset 1px 0 0 var(--lg-divider); }
.sidebar-pane headerbar, .sidebar-pane .top-bar { box-shadow: none; }
.navigation-sidebar { background: transparent; }
.navigation-sidebar > row, .navigation-sidebar > row.activatable {
  border-radius: $radius_menu_item;
  margin: 1px 6px;
}
.navigation-sidebar > row:hover { background-color: var(--lg-hover); }
.navigation-sidebar > row:selected, .navigation-sidebar > row:selected:hover {
  background-color: var(--lg-glass-hi);
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge);
}
placessidebar .navigation-sidebar > row { margin: 1px 6px; }
placessidebar list { background: transparent; }

/* ---- content views stay more solid than the chrome ------------------------ */
.view, textview > text, iconview, listview, columnview, gridview { background-color: transparent; }
scrolledwindow > .view, scrolledwindow > listview, scrolledwindow > gridview,
scrolledwindow > columnview, scrolledwindow > textview, scrolledwindow > treeview,
textview > text {
  background-color: var(--view-bg-color);
}
scrolledwindow > listview, scrolledwindow > gridview, scrolledwindow > columnview,
scrolledwindow > treeview, scrolledwindow > iconview { background-color: var(--view-bg-color); }
.view:selected, .view:selected:focus, iconview:selected, gridview > child:selected,
textview > text:selected {
  background-color: var(--lg-selection);
}
row:selected, listview > row:selected, columnview > listview > row:selected {
  background-color: var(--lg-selection);
}
row:hover:not(:selected), listview > row:hover:not(:selected), gridview > child:hover:not(:selected) {
  background-color: var(--lg-hover);
}
gridview > child { border-radius: $radius_card; }
columnview > header { background-color: transparent; box-shadow: inset 0 -1px 0 var(--lg-divider); }
columnview > header > button, treeview > header > button { background: transparent; border-radius: 0; box-shadow: none; }
separator { background-color: var(--lg-divider); }

/* ---- cards, boxed lists, preference groups ------------------------------- */
.card, list.boxed-list, list.content, .boxed-list-separate > row, list.boxed-list-separate > row {
  border-radius: $radius_card;
  background-color: var(--card-bg-color);
  box-shadow:
    inset 0 1px 0 var(--lg-rim),
    inset 0 0 0 1px var(--lg-edge),
    0 2px 10px 0 var(--lg-shadow);
}
list.boxed-list > row, list.content > row { box-shadow: none; background-color: transparent; border-bottom-color: var(--lg-divider); }
list.boxed-list > row:hover, list.content > row:hover { background-color: var(--lg-hover); }
list.boxed-list > row:selected { background-color: var(--lg-selection); }
list.boxed-list-separate > row, list.navigation-sidebar.boxed-list-separate > row { margin: 0; }
row.expander row.header:hover { background-color: var(--lg-hover); }
.card.activatable:hover { background-color: color-mix(in srgb, var(--card-bg-color), var(--lg-hover)); }
preferencespage > scrolledwindow > viewport > clamp > box > preferencesgroup > box > box > list.boxed-list { background: var(--card-bg-color); }

/* ---- buttons: glass pills ---------------------------------------------- */
button { border-radius: 999px; }
button.flat, button.image-button.flat, headerbar button.flat, .toolbar button.flat {
  background-color: transparent;
  box-shadow: none;
  background-image: none;
}
button.flat:hover, button.flat:checked { background-color: var(--lg-hover); }
button.flat:active { background-color: var(--lg-active); }
$glass_btn {
  background-color: var(--lg-glass);
  background-image: linear-gradient(to bottom, var(--lg-sheen-top), var(--lg-sheen-bottom) 70%);
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge), 0 1px 3px 0 var(--lg-shadow);
}
$glass_btn:hover { background-color: var(--lg-glass-hi); }
$glass_btn:active, $glass_btn:checked {
  background-color: var(--lg-glass-hi);
  background-image: none;
  box-shadow: inset 0 1px 3px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge);
}
button.suggested-action, button.destructive-action, button.opaque {
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0) 60%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), inset 0 0 0 1px rgba(255, 255, 255, 0.10), 0 2px 8px 0 var(--lg-shadow);
}
button.suggested-action:hover, button.destructive-action:hover, button.opaque:hover {
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.30), rgba(255, 255, 255, 0.04) 60%);
}
button.pill, button.card { border-radius: 999px; }
button.card { border-radius: $radius_card; }
.linked > button:not(:first-child):not(:last-child) { border-radius: 0; }
.linked > button:first-child:not(:last-child) { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.linked > button:last-child:not(:first-child) { border-top-left-radius: 0; border-bottom-left-radius: 0; }
.linked:not(.vertical) > button:first-child:not(:last-child) { border-radius: 999px 0 0 999px; }
.linked:not(.vertical) > button:last-child:not(:first-child) { border-radius: 0 999px 999px 0; }
.linked.vertical > button:first-child:not(:last-child) { border-radius: $radius_small $radius_small 0 0; }
.linked.vertical > button:last-child:not(:first-child) { border-radius: 0 0 $radius_small $radius_small; }
splitbutton > button, splitbutton > menubutton > button { border-radius: 0; }
splitbutton > button:first-child { border-radius: 999px 0 0 999px; }
splitbutton > menubutton:last-child > button { border-radius: 0 999px 999px 0; }
button.osd, .osd button { background-color: rgba(20, 20, 24, 0.55); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28), inset 0 0 0 1px rgba(255, 255, 255, 0.10); }
menubutton > button, dropdown > button, combobox button.combo { border-radius: 999px; }
button.destructive-action { color: var(--destructive-fg-color); }

/* ---- header bar buttons: flat icons on one glass bar -------------------------
   No bubbles at rest. Hovering a button lifts a glass tile under that one button,
   pressing it thins the tile and dips the icon. Calls to action (Save, Delete)
   stay filled. The tile fades in quickly and out slowly. */
$hdr_btn {
  border-radius: 8px;
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  color: color-mix(in srgb, currentColor 85%, transparent);
  transition: background-color 200ms ease-out, box-shadow 200ms ease-out, color 200ms ease-out;
}
$hdr_btn_hover, $hdr_btn_checked {
  background-color: var(--lg-tile);
  background-image: none;
  box-shadow: inset 0 1px 0 var(--lg-rim);
  color: var(--headerbar-fg-color);
  transition-duration: 120ms;
}
$hdr_btn_checked { color: var(--accent-color); }
$hdr_btn_active {
  background-color: var(--lg-tile-press);
  background-image: none;
  box-shadow: inset 0 1px 2px 0 var(--lg-shadow);
  transition-duration: 60ms;
}
$hdr_btn_icon { transition: -gtk-icon-transform 160ms cubic-bezier(0.34, 1.56, 0.64, 1); }
$hdr_btn_icon_active { -gtk-icon-transform: scale(0.94); transition-duration: 60ms; }

/* Window controls: the same flat glyphs and tile. Close turns soft red on hover only. */
windowcontrols > button {
  border-radius: 8px;
  background-color: transparent;
  box-shadow: none;
  color: color-mix(in srgb, var(--headerbar-fg-color) 85%, transparent);
  transition: background-color 200ms ease-out, box-shadow 200ms ease-out, color 200ms ease-out;
}
windowcontrols > button > image, windowcontrols > button:hover > image, windowcontrols > button:active > image {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  transition: -gtk-icon-transform 160ms cubic-bezier(0.34, 1.56, 0.64, 1);
}
windowcontrols > button:hover {
  background-color: var(--lg-tile);
  box-shadow: inset 0 1px 0 var(--lg-rim);
  color: var(--headerbar-fg-color);
  transition-duration: 120ms;
}
windowcontrols > button:active { background-color: var(--lg-tile-press); box-shadow: inset 0 1px 2px 0 var(--lg-shadow); }
windowcontrols > button:active > image { -gtk-icon-transform: scale(0.94); }
windowcontrols > button.close:hover, windowcontrols > button.close:active { background-color: var(--lg-close); box-shadow: none; color: white; }

/* Unfocused windows: libadwaita fades the whole bar to 50%, which on top of the
   icons' own 85% nearly hides them. Fade bars to 65% instead (titles, icons and
   text buttons alike), keeping libadwaita's rule that nested bars fade only once. */
headerbar:backdrop > windowhandle,
toolbarview > .top-bar:backdrop > windowhandle, toolbarview > .bottom-bar:backdrop > windowhandle,
tabbar .box:backdrop > scrolledwindow, tabbar .box:backdrop > .start-action, tabbar .box:backdrop > .end-action {
  filter: opacity(0.65);
  transition: filter 120ms ease-out;
}
toolbarview > .top-bar headerbar:backdrop > windowhandle, toolbarview > .bottom-bar headerbar:backdrop > windowhandle,
toolbarview > .top-bar tabbar .box:backdrop > scrolledwindow, toolbarview > .bottom-bar tabbar .box:backdrop > scrolledwindow,
toolbarview > .top-bar tabbar .box:backdrop > .start-action, toolbarview > .bottom-bar tabbar .box:backdrop > .start-action,
toolbarview > .top-bar tabbar .box:backdrop > .end-action, toolbarview > .bottom-bar tabbar .box:backdrop > .end-action,
tabbar.inline .box:backdrop > scrolledwindow, tabbar.inline .box:backdrop > .start-action, tabbar.inline .box:backdrop > .end-action {
  filter: none;
}

/* ---- entries, search, spin buttons ----------------------------------------- */
entry, spinbutton, searchentry, row.entry, row.spin {
  border-radius: 999px;
  min-height: 36px;
  background-color: var(--lg-glass);
  box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge), 0 1px 0 0 var(--lg-rim);
}
entry:focus-within, spinbutton:focus-within {
  background-color: var(--lg-glass-hi);
  box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-accent-text), 0 0 0 3px color-mix(in srgb, var(--lg-accent) 35%, transparent);
  outline: none;
}
row.entry, row.spin, row.entry:focus-within { border-radius: $radius_small; box-shadow: none; background-color: transparent; }
textview { border-radius: $radius_small; }
spinbutton > button { border-radius: 999px; }
treeview entry, treeview entry.flat { border-radius: 0; box-shadow: none; }
searchentry { padding-left: 8px; }
entry > text > selection, textview > text > selection, label > selection { background-color: var(--lg-selection); }
entry.error, spinbutton.error { box-shadow: inset 0 0 0 1px var(--destructive-color), 0 0 0 3px color-mix(in srgb, var(--destructive-color) 30%, transparent); }

/* ---- switches, check/radio, scale, progress -------------------------------- */
switch {
  border-radius: 999px;
  background-color: var(--lg-glass-hi);
  box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge);
}
switch:checked {
  background-color: var(--accent-bg-color);
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.20), rgba(255, 255, 255, 0) 70%);
  box-shadow: inset 0 1px 2px 0 rgba(0, 0, 0, 0.25), inset 0 0 0 1px rgba(255, 255, 255, 0.12);
}
switch > slider {
  border-radius: 999px;
  background-color: #ffffff;
  background-image: linear-gradient(to bottom, #ffffff, #e9ebf2);
  box-shadow: inset 0 1px 0 #ffffff, 0 2px 6px 0 rgba(0, 0, 0, 0.45), 0 0 0 0.5px rgba(0, 0, 0, 0.25);
  border: none;
}
check, radio {
  background-color: var(--lg-glass-hi);
  box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge);
}
check:checked, radio:checked, check:indeterminate, radio:indeterminate {
  background-color: var(--accent-bg-color);
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0) 70%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4), 0 1px 3px 0 var(--lg-shadow);
}
scale > trough, progressbar > trough {
  background-color: var(--lg-glass-hi);
  box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge);
}
scale > trough > highlight, progressbar > trough > progress {
  background-color: var(--accent-bg-color);
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.28), rgba(255, 255, 255, 0) 80%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35);
}
scale > trough > slider {
  background-color: #ffffff;
  background-image: linear-gradient(to bottom, #ffffff, #e9ebf2);
  box-shadow: inset 0 1px 0 #ffffff, 0 2px 6px 0 rgba(0, 0, 0, 0.45), 0 0 0 0.5px rgba(0, 0, 0, 0.25);
}
scale > trough > slider:hover { background-image: linear-gradient(to bottom, #ffffff, #f4f6fb); }
levelbar > trough > block.filled { background-color: var(--accent-bg-color); }
levelbar > trough > block.empty { background-color: var(--lg-glass-hi); }
scrollbar > range > trough > slider { background-color: var(--lg-fg-faint); }
scrollbar.overlay-indicator:not(.hovering) > range > trough > slider { background-color: var(--lg-fg-dim); }

/* ---- popovers and menus: the most solid glass, they have no blur behind ----- */
popover > contents {
  border-radius: $radius_popover;
  background-color: var(--popover-bg-color);
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0) 40%);
  box-shadow:
    inset 0 1px 0 var(--lg-rim),
    inset 0 0 0 1px var(--lg-edge),
    0 0 0 1px rgba(0, 0, 0, 0.30),
    0 12px 32px 0 var(--lg-deep-shadow),
    0 2px 8px 0 var(--lg-shadow);
  border: none;
}
popover > arrow { background-color: var(--popover-bg-color); box-shadow: none; border: none; }
popover.menu > contents { padding: 0; }
popover.menu modelbutton, popover modelbutton { border-radius: $radius_menu_item; }
popover.menu modelbutton:hover, popover.menu modelbutton:selected { background-color: var(--lg-glass-hi); }
popover.menu separator, popover separator { background-color: var(--lg-divider); }
popover > contents > list, popover > contents > .view, popover > contents > toolbar { background-color: transparent; }
popover entry, popover searchentry { box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge); }
popover.background > contents scrolledwindow > .view, popover scrolledwindow > listview { background-color: transparent; }

/* ---- dialogs and sheets -------------------------------------------------------- */
window.dialog, window.dialog-window, window.messagedialog, window.print { background-color: var(--dialog-bg-color); }
window.dialog.csd, window.messagedialog.csd { border-radius: $radius_window; }
dialog-host > dialog.background sheet, dialog-host > dialog.alert sheet, dialog-host > dialog sheet {
  background-color: var(--dialog-bg-color);
  border-radius: $radius_window;
  box-shadow:
    inset 0 1px 0 var(--lg-rim),
    inset 0 0 0 1px var(--lg-edge),
    0 0 0 1px rgba(0, 0, 0, 0.30),
    0 18px 48px 4px var(--lg-deep-shadow);
}
dialog-host > dialog.bottom-sheet sheet, bottom-sheet > sheet {
  background-color: var(--dialog-bg-color);
  box-shadow: inset 0 1px 0 var(--lg-rim), 0 -8px 32px 0 var(--lg-deep-shadow);
}
dialog-host > dialog.alert sheet { border-radius: $radius_window; }
dialog-host > dialog.alert sheet button { min-height: 38px; }
dialog-host > dialog sheet headerbar { background: transparent; }
window.dialog-window headerbar, window.messagedialog headerbar { box-shadow: none; }
bottom-sheet > dimming, dialog-host > dialog > dimming, dialog-host > dialog.floating > dimming { background-color: rgba(0, 0, 0, 0.28); }

/* ---- tooltips, toasts, banners, OSD ---------------------------------------- */
tooltip.background {
  background-color: var(--lg-tooltip);
  color: var(--lg-tooltip-fg);
  border-radius: $radius_menu_item;
  border: none;
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge), 0 6px 18px 0 var(--lg-deep-shadow);
}
toast, .app-notification {
  background-color: var(--lg-tooltip);
  color: var(--lg-tooltip-fg);
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0));
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge), 0 10px 28px 0 var(--lg-deep-shadow);
}
banner > revealer > widget {
  background-color: color-mix(in srgb, var(--accent-bg-color) 55%, transparent);
  box-shadow: inset 0 -1px 0 var(--lg-edge);
}
.osd:not(button):not(progressbar):not(popover):not(.flat) {
  background-color: var(--lg-tooltip);
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge), 0 8px 24px 0 var(--lg-deep-shadow);
}
.osd:not(button):not(progressbar):not(popover) { color: var(--lg-tooltip-fg); }
progressbar.osd > trough > progress { background-color: var(--lg-tooltip-fg); background-image: none; box-shadow: none; }
progressbar.osd { background: transparent; box-shadow: none; }

/* ---- tabs, view switchers -------------------------------------------------------- */
tabbar tabbox > tab, tabbar tabbox > tabboxchild { border-radius: 999px; }
tabbar tabbox > tabboxchild:selected, tabbar tabbox > tab:selected {
  background-color: var(--lg-glass-hi);
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge);
}
tabbar tabbox > tabboxchild:hover:not(:selected) { background-color: var(--lg-hover); }
notebook > header { background-color: transparent; box-shadow: inset 0 -1px 0 var(--lg-divider); }
notebook > header > tabs > tab { border-radius: $radius_menu_item $radius_menu_item 0 0; }
notebook > header > tabs > tab:checked { background-color: var(--lg-glass-hi); box-shadow: inset 0 1px 0 var(--lg-rim); }
notebook > stack { background-color: var(--view-bg-color); }
viewswitcher button.toggle, inline-view-switcher button, toggle-group button {
  border-radius: 999px;
}
viewswitcher button.toggle:checked, inline-view-switcher button:checked {
  background-color: var(--lg-glass-hi);
  box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge);
}
toggle-group, inline-view-switcher {
  border-radius: 999px;
  background-color: var(--lg-glass);
  box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge);
}
toggle-group button:checked, toggle-group > toggle:checked {
  background-color: var(--active-toggle-bg-color);
  background-image: none;
  box-shadow: inset 0 1px 0 var(--lg-rim), 0 1px 4px 0 var(--lg-shadow);
}

/* ---- Nautilus ---------------------------------------------------------------------- */
/* Files' path bar is one glass field: the location and the ⋮ menu share one fill. */
.nautilus-pathbar, pathbar { background-color: var(--lg-glass); border-radius: 999px; box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge); }
.path-bar-box { background-color: var(--lg-glass); border-radius: 999px; box-shadow: inset 0 1px 2px 0 var(--lg-shadow), inset 0 0 0 1px var(--lg-edge); padding: 2px; }
.nautilus-pathbar > menubutton > button { margin: 3px; }
.nautilus-pathbar .path-bar-box { background: none; box-shadow: none; padding: 0; }
.nautilus-pathbar > scrolledwindow:dir(ltr) undershoot.left { border-radius: 999px 0 0 999px; }
.nautilus-pathbar > scrolledwindow:dir(rtl) undershoot.right { border-radius: 0 999px 999px 0; }
.path-bar-box button, pathbar button { border-radius: 999px; background: transparent; box-shadow: none; min-height: 28px; }
.path-bar-box button.current-dir, pathbar button:checked, .path-bar-box button:checked { background-color: var(--lg-glass-hi); box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge); }
/* Folder segments sit flat inside the field (Files marks the current one in bold);
   hovering a parent folder lifts the same glass tile as header buttons. */
$path_btn { background: none; box-shadow: none; border-radius: 999px; }
$path_btn_hover { background-color: var(--lg-tile); box-shadow: inset 0 1px 0 var(--lg-rim); }
NautilusViewCell, .nautilus-grid-view > child { border-radius: $radius_card; }
.nautilus-window .view, window.nautilus .view { background-color: var(--view-bg-color); }
.floating-bar, .nautilus-floating-bar { border-radius: 999px; background-color: var(--popover-bg-color); box-shadow: inset 0 1px 0 var(--lg-rim), inset 0 0 0 1px var(--lg-edge), 0 4px 14px 0 var(--lg-shadow); }
.nautilus-grid-view > child:selected { background-color: var(--lg-selection); box-shadow: inset 0 1px 0 var(--lg-rim); }

/* ---- Ptyxis: chrome only, the terminal surface keeps its own colours/opacity ---- */
/* The top edge's light is the Shell's real reflection; no painted line here. */
revealer.top-bar > windowhandle { box-shadow: inset 0 -1px 0 var(--lg-divider); }

/* ---- misc --------------------------------------------------------------------------- */
*:focus-visible { outline-color: color-mix(in srgb, var(--lg-accent-text) 70%, transparent); }
statuspage > scrolledwindow > viewport > clamp > box > .icon, statuspage .icon { opacity: 0.6; }
