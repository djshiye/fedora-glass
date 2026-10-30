/* ---- windows ---------------------------------------------------------------- */
window.background { background-color: @window_bg_color; color: @window_fg_color; }
window.csd, window.csd.background { border-radius: $radius_window; }
window.csd > decoration, decoration {
  border-radius: $radius_window;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.30),
    0 18px 44px 2px @lg_deep_shadow,
    0 4px 12px 0 @lg_shadow;
  margin: 24px;
}
window.csd.maximized > decoration, window.csd.fullscreen > decoration, window.csd.tiled > decoration {
  border-radius: 0; box-shadow: none; margin: 0;
}
window.csd:backdrop > decoration {
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.22), 0 8px 24px 2px @lg_shadow;
}

/* ---- header bars -------------------------------------------------------------- */
/* GTK 3 draws the window background below the title bar only, so the bar paints the same glass itself. */
headerbar, .titlebar, headerbar:backdrop, .titlebar:backdrop {
  background-color: @window_bg_color;
  background-image: none;
  color: @headerbar_fg_color;
  border: none;
  box-shadow: inset 0 -1px 0 @lg_divider;
  border-radius: 0;
}
window.csd > .titlebar, window.csd > headerbar { border-top-left-radius: $radius_window; border-top-right-radius: $radius_window; box-shadow: inset 0 -1px 0 @lg_divider; }
headerbar.selection-mode { background-color: @accent_bg_color; color: @accent_fg_color; }
searchbar, .search-bar, actionbar { background-color: @lg_bar; border: none; box-shadow: inset 0 -1px 0 @lg_divider; }
actionbar { box-shadow: inset 0 1px 0 @lg_divider; }

/* ---- sidebars --------------------------------------------------------------------- */
.sidebar, placessidebar, stacksidebar, placessidebar.sidebar {
  background-color: @sidebar_bg_color;
  color: @sidebar_fg_color;
  border-color: @lg_divider;
}
placessidebar list, stacksidebar list, .sidebar list { background-color: transparent; }
placessidebar row, stacksidebar row, .sidebar row {
  border-radius: $radius_menu_item;
  margin: 1px 6px;
}
placessidebar row:hover, stacksidebar row:hover { background-color: @lg_hover; }
placessidebar row:selected, stacksidebar row:selected, .sidebar row:selected {
  background-color: @lg_glass_hi;
  color: @sidebar_fg_color;
  box-shadow: inset 0 1px 0 @lg_rim, inset 0 0 0 1px @lg_edge;
}

/* ---- views, lists -------------------------------------------------------------------- */
.view, iconview, textview text, treeview.view, list, .content-view { background-color: @view_bg_color; color: @view_fg_color; }
list row, .content-view .view { background-color: transparent; }
.view:selected, iconview:selected, textview text:selected, treeview.view:selected, row:selected,
.view:selected:focus, treeview.view:selected:focus {
  background-color: @lg_selection;
  color: @view_fg_color;
  border-radius: $radius_small;
}
row:hover:not(:selected) { background-color: @lg_hover; }
treeview.view header button { background-color: transparent; background-image: none; border-radius: 0; box-shadow: inset 0 -1px 0 @lg_divider; }
scrolledwindow { border-color: @lg_divider; }
separator { background-color: @lg_divider; }
frame > border, .frame { border-color: @lg_edge; }

/* ---- buttons ---------------------------------------------------------------------------- */
button {
  border-radius: 999px;
  min-height: 24px;
  padding: 4px 14px;
  border: none;
  background-color: @lg_glass;
  background-image: linear-gradient(to bottom, @lg_sheen_top, @lg_sheen_bottom);
  color: @window_fg_color;
  box-shadow: inset 0 1px 0 @lg_rim, inset 0 0 0 1px @lg_edge, 0 1px 3px 0 @lg_shadow;
}
button:hover { background-color: @lg_glass_hi; }
button:active, button:checked {
  background-color: @lg_glass_hi;
  background-image: none;
  box-shadow: inset 0 1px 3px 0 @lg_shadow, inset 0 0 0 1px @lg_edge;
}
button:disabled { opacity: 0.5; }
button.flat, headerbar button.flat, .titlebar button.flat, toolbar button.flat, .path-bar button {
  background-color: transparent; background-image: none; box-shadow: none;
}
button.flat:hover, button.flat:checked, .path-bar button:hover { background-color: @lg_hover; }
button.flat:active { background-color: @lg_active; }
button.image-button { padding: 4px 8px; min-width: 24px; }
button.suggested-action, button.destructive-action {
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0) 60%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), inset 0 0 0 1px rgba(255, 255, 255, 0.10), 0 2px 8px 0 @lg_shadow;
}
button.suggested-action { background-color: @accent_bg_color; color: @accent_fg_color; }
button.destructive-action { background-color: @destructive_bg_color; color: @destructive_fg_color; }
.linked > button:not(:first-child):not(:last-child) { border-radius: 0; }
.linked:not(.vertical) > button:first-child:not(:last-child) { border-radius: 999px 0 0 999px; }
.linked:not(.vertical) > button:last-child:not(:first-child) { border-radius: 0 999px 999px 0; }

/* ---- header bar buttons: flat icons on one glass bar (same look as GTK 4) ---------------------- */
headerbar button:not(.suggested-action):not(.destructive-action):not(.titlebutton),
.titlebar button:not(.suggested-action):not(.destructive-action):not(.titlebutton),
headerbar .linked:not(.vertical) > button:not(.suggested-action):not(.destructive-action),
.titlebar .linked:not(.vertical) > button:not(.suggested-action):not(.destructive-action) {
  border-radius: 8px;
  border: none;
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  text-shadow: none;
  -gtk-icon-shadow: none;
  color: alpha(@headerbar_fg_color, 0.9);
  transition: background-color 200ms ease-out, box-shadow 200ms ease-out;
}
headerbar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):backdrop,
.titlebar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):backdrop { color: alpha(@headerbar_fg_color, 0.65); }
headerbar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):hover,
.titlebar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):hover,
headerbar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):checked,
.titlebar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):checked {
  background-color: @lg_tile;
  box-shadow: inset 0 1px 0 @lg_rim;
  color: @headerbar_fg_color;
  transition-duration: 120ms;
}
headerbar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):checked,
.titlebar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):checked { color: @accent_color; }
headerbar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):active,
.titlebar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):active {
  background-color: @lg_tile_press;
  box-shadow: inset 0 1px 2px 0 @lg_shadow;
}
headerbar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):active image,
.titlebar button:not(.suggested-action):not(.destructive-action):not(.titlebutton):active image { -gtk-icon-transform: scale(0.94); }

/* Window controls: flat glyphs, the same tile on hover, Close turns soft red. */
.titlebutton, headerbar .titlebutton, .titlebar .titlebutton {
  border-radius: 8px; padding: 4px; min-height: 16px; min-width: 16px;
  /* Other GTK 3 themes (Orchis, for one) paint window buttons with coloured dots,
     image assets and a transparent glyph: reset all of it so only our look shows. */
  border: none; animation: none;
  background-color: transparent; background-image: none; box-shadow: none;
  text-shadow: none; -gtk-icon-shadow: none;
  color: alpha(@headerbar_fg_color, 0.9);
}
headerbar .titlebutton:backdrop, .titlebar .titlebutton:backdrop { color: alpha(@headerbar_fg_color, 0.65); }
headerbar .titlebutton:hover, .titlebar .titlebutton:hover {
  background-color: @lg_tile;
  box-shadow: inset 0 1px 0 @lg_rim;
  color: @headerbar_fg_color;
}
headerbar .titlebutton:active, .titlebar .titlebutton:active { background-color: @lg_tile_press; }
headerbar .titlebutton.close:hover, .titlebar .titlebutton.close:hover,
headerbar .titlebutton.close:active, .titlebar .titlebutton.close:active { background-color: @lg_close; box-shadow: none; color: white; }

/* ---- entries ----------------------------------------------------------------------------------- */
entry, spinbutton {
  border-radius: 999px;
  min-height: 28px;
  padding: 2px 12px;
  border: none;
  background-color: @lg_glass;
  background-image: none;
  color: @view_fg_color;
  box-shadow: inset 0 1px 2px 0 @lg_shadow, inset 0 0 0 1px @lg_edge, 0 1px 0 0 @lg_rim;
}
entry:focus, spinbutton:focus-within {
  background-color: @lg_glass_hi;
  box-shadow: inset 0 1px 2px 0 @lg_shadow, inset 0 0 0 1px @accent_color, 0 0 0 3px alpha(@accent_bg_color, 0.35);
}
entry selection, textview text selection { background-color: @lg_selection; }
spinbutton button { border-radius: 999px; box-shadow: none; background-image: none; }
treeview entry { border-radius: 0; box-shadow: none; }

/* ---- switches, checks, scales, progress ------------------------------------------------------------ */
switch {
  border-radius: 999px;
  background-color: @lg_glass_hi;
  background-image: none;
  border: none;
  box-shadow: inset 0 1px 2px 0 @lg_shadow, inset 0 0 0 1px @lg_edge;
}
switch:checked { background-color: @accent_bg_color; box-shadow: inset 0 1px 2px 0 rgba(0, 0, 0, 0.25), inset 0 0 0 1px rgba(255, 255, 255, 0.12); }
switch slider {
  border-radius: 999px;
  border: none;
  background-color: #ffffff;
  background-image: linear-gradient(to bottom, #ffffff, #e9ebf2);
  box-shadow: inset 0 1px 0 #ffffff, 0 2px 6px 0 rgba(0, 0, 0, 0.45);
}
check, radio { background-color: @lg_glass_hi; background-image: none; border: none; box-shadow: inset 0 1px 2px 0 @lg_shadow, inset 0 0 0 1px @lg_edge; }
check:checked, radio:checked, check:indeterminate, radio:indeterminate {
  background-color: @accent_bg_color; color: @accent_fg_color;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4), 0 1px 3px 0 @lg_shadow;
}
scale trough, progressbar trough, levelbar trough {
  border-radius: 999px; border: none; background-image: none;
  background-color: @lg_glass_hi;
  box-shadow: inset 0 1px 2px 0 @lg_shadow, inset 0 0 0 1px @lg_edge;
}
scale trough { min-height: 6px; min-width: 6px; }
scale.horizontal trough, scale.horizontal highlight { min-height: 6px; }
scale.vertical trough, scale.vertical highlight { min-width: 6px; }
progressbar trough, progressbar progress { min-height: 6px; }
scale highlight, progressbar progress, levelbar block.filled {
  border-radius: 999px; border: none;
  background-color: @accent_bg_color;
  background-image: linear-gradient(to bottom, rgba(255, 255, 255, 0.28), rgba(255, 255, 255, 0) 80%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35);
}
scale slider {
  min-width: 18px; min-height: 18px; margin: -7px;
  border-radius: 999px; border: none;
  background-color: #ffffff;
  background-image: linear-gradient(to bottom, #ffffff, #e9ebf2);
  box-shadow: inset 0 1px 0 #ffffff, 0 2px 6px 0 rgba(0, 0, 0, 0.45);
}

/* ---- popovers and menus ----------------------------------------------------------------------------------- */
popover.background, popover {
  border-radius: $radius_popover;
  border: none;
  background-color: @popover_bg_color;
  color: @popover_fg_color;
  box-shadow: inset 0 1px 0 @lg_rim, inset 0 0 0 1px @lg_edge, 0 0 0 1px rgba(0, 0, 0, 0.30), 0 12px 32px 0 @lg_deep_shadow;
}
popover.background > box, popover > box { background-color: transparent; }
popover modelbutton { border-radius: $radius_menu_item; }
popover modelbutton:hover { background-color: @lg_glass_hi; }
menu, .menu, .context-menu {
  border-radius: $radius_popover;
  border: none;
  padding: 6px;
  background-color: @popover_bg_color;
  color: @popover_fg_color;
  box-shadow: inset 0 1px 0 @lg_rim, inset 0 0 0 1px @lg_edge, 0 12px 32px 0 @lg_deep_shadow;
}
menu menuitem, .menu menuitem { border-radius: $radius_menu_item; padding: 6px 10px; }
menu menuitem:hover, .menu menuitem:hover { background-color: @lg_glass_hi; color: @popover_fg_color; }
menu separator, .menu separator { background-color: @lg_divider; }
.csd menu, .csd .menu { border-radius: $radius_popover; }

/* ---- dialogs, tooltips, notifications ------------------------------------------------------------------------- */
window.dialog.background, messagedialog.background, window.messagedialog { background-color: @dialog_bg_color; color: @dialog_fg_color; }
tooltip, tooltip.background {
  border-radius: $radius_menu_item;
  border: none;
  background-color: @lg_tooltip;
  color: @lg_tooltip_fg;
  box-shadow: inset 0 1px 0 @lg_rim, inset 0 0 0 1px @lg_edge, 0 6px 18px 0 @lg_deep_shadow;
}
tooltip * { color: @lg_tooltip_fg; }
.app-notification, .osd { background-color: @lg_tooltip; color: @lg_tooltip_fg; box-shadow: inset 0 1px 0 @lg_rim, inset 0 0 0 1px @lg_edge, 0 10px 28px 0 @lg_deep_shadow; border: none; }
infobar > revealer > box, infobar { background-color: alpha(@accent_bg_color, 0.55); border: none; }

/* ---- tabs ------------------------------------------------------------------------------------------------------------ */
notebook > header { background-color: transparent; box-shadow: inset 0 -1px 0 @lg_divider; border: none; }
notebook > header > tabs > tab { border-radius: $radius_menu_item $radius_menu_item 0 0; border: none; background-image: none; }
notebook > header > tabs > tab { color: @theme_fg_color; }
notebook > header > tabs > tab:hover { background-color: @lg_hover; }
/* The open tab: full-strength text and an accent line, so it reads in light and dark alike. */
notebook > header > tabs > tab:checked { color: @theme_fg_color; background-color: @lg_glass_hi; box-shadow: inset 0 1px 0 @lg_rim, inset 0 -2px 0 @lg_accent; }
notebook > stack { background-color: @view_bg_color; }
stackswitcher button { border-radius: 999px; }

/* ---- Nautilus-like file managers, path bars, scrollbars ----------------------------------------------------------------------- */
.path-bar button, pathbar button { border-radius: 999px; }
scrollbar slider { border-radius: 999px; background-color: @lg_fg_faint; border: none; min-width: 6px; min-height: 6px; }
scrollbar.overlay-indicator:not(.hovering) slider { background-color: @lg_fg_dim; }
scrollbar trough { background-color: transparent; border: none; }
