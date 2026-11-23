"""A window split into a white half and a black half, with one pop-up open across the split.

    pop-board.py 4|3        GTK 4 or GTK 3

The release check compares the pop-up's colour over the two halves: any difference is the
window showing through it. The pop-up is empty, so nothing of its own differs left to right."""
import sys

import gi

KIT = sys.argv[1] if len(sys.argv) > 1 else "4"
gi.require_version("Gtk", f"{KIT}.0")
gi.require_version("Gdk", f"{KIT}.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

POP_W, POP_H, POP_Y = 340, 260, 40
# The halves are plain boxes filled by a style sheet (the test desktop has no cairo for Python).
CSS = ".pb-white { background: #ffffff; } .pb-black { background: #000000; }"


def at_split(width: int) -> Gdk.Rectangle:
    r = Gdk.Rectangle()
    r.x, r.y, r.width, r.height = width // 2, POP_Y, 1, 1
    return r


def gtk4() -> None:
    app = Gtk.Application(application_id="org.lgqa.PopBoard4")

    def build(app: Gtk.Application) -> None:
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = Gtk.ApplicationWindow(application=app, title="PopBoard GTK 4", default_width=760, default_height=520)
        board = Gtk.Box(homogeneous=True, hexpand=True, vexpand=True)
        for half in ("pb-white", "pb-black"):
            board.append(Gtk.Box(css_classes=[half], hexpand=True))
        win.set_child(board)
        win.present()
        pop = Gtk.Popover(autohide=False, position=Gtk.PositionType.BOTTOM)
        pop.set_child(Gtk.Box(width_request=POP_W, height_request=POP_H))
        pop.set_parent(board)

        def show() -> bool:
            pop.set_pointing_to(at_split(board.get_width()))
            pop.popup()
            return False
        GLib.timeout_add(1500, show)

    app.connect("activate", build)
    app.run([])


def gtk3() -> None:
    css = Gtk.CssProvider()
    css.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    win = Gtk.Window(title="PopBoard GTK 3", default_width=760, default_height=520)
    board = Gtk.Box(homogeneous=True)
    for half in ("pb-white", "pb-black"):
        box = Gtk.Box()
        box.get_style_context().add_class(half)
        board.pack_start(box, True, True, 0)
    win.add(board)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    pop = Gtk.Popover.new(board)
    pop.set_modal(False)
    pop.set_position(Gtk.PositionType.BOTTOM)
    body = Gtk.Box(width_request=POP_W, height_request=POP_H)
    body.show()
    pop.add(body)

    def show() -> bool:
        pop.set_pointing_to(at_split(board.get_allocated_width()))
        pop.popup()
        return False
    GLib.timeout_add(1500, show)
    Gtk.main()


gtk4() if KIT == "4" else gtk3()
