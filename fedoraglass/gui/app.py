"""Fedora Glass customizer: a Qt Quick window over the engine.

`python3 -m fedoraglass gui` lands here. `--screenshot PATH` renders the
window to a PNG once it has settled (for docs and tests) and quits.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import sys
from pathlib import Path

from .. import APP_ID, __version__

HERE = Path(__file__).resolve().parent
QML_DIR = HERE / "qml"
PAGE_IDS = ("home", "colour", "glass", "windows", "motion", "pointer", "lock", "apps", "advanced", "about")
# Older names still work: the Look page's sections and the page numbers 0 (Look), 1 (Apps), 2 (Lock).
PAGE_ALIASES = {"look": "home", "0": "home", "1": "apps", "2": "lock", "more": "advanced",
                "desktop": "pointer"}


def find_icon() -> Path | None:
    """The SVG ships in data/icons next to the package, or in the icon theme once installed."""
    name = f"{APP_ID}.svg"
    for base in (HERE.parent.parent / "data/icons", HERE.parent / "data/icons",
                 Path.home() / ".local/share/icons/hicolor/scalable/apps",
                 Path("/usr/share/icons/hicolor/scalable/apps")):
        if (base / name).is_file():
            return base / name
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="fedora-glass gui", description="Fedora Glass customizer")
    shot = ap.add_argument_group("screenshots")
    shot.add_argument("--screenshot", metavar="PATH", help="render the window to a PNG, then quit")
    shot.add_argument("--page", default="home", help="page to show: " + ", ".join(PAGE_IDS))
    shot.add_argument("--lock-preview", choices=("rest", "prompt"), help="the moment the lock screen preview shows")
    shot.add_argument("--frost", type=float, help="set the frost slider (0..1) without saving")
    shot.add_argument("--scheme", choices=("dark", "light"), help="force the app and preview style")
    shot.add_argument("--held", action="store_true", help="draw the frost knob as if it were being dragged")
    shot.add_argument("--fine-tune", action="store_true", help="open the Fine-tune section")
    shot.add_argument("--section", help="same as --page (the old Look page sections are pages now)")
    shot.add_argument("--reveal", metavar="NAME", help="open the page's fold around this control and light it up, as search does")
    shot.add_argument("--scroll", type=float, default=0, help="scroll the options column down this far, in px")
    shot.add_argument("--sheet", choices=("changes", "results", "restore", "leave", "welcome", "about"), help="open a sheet")
    shot.add_argument("--dropdown", metavar="NAME", help="open the dropdown with this objectName")
    shot.add_argument("--tip", metavar="NAME", help="show the tooltip of the control with this objectName")
    shot.add_argument("--preview-scene", choices=("desktop", "quicksettings", "calendar", "overview"),
                      help="what the preview shows")
    shot.add_argument("--preview-pointer", metavar="X,Y",
                      help="hold a pointer over the preview at these px of its 1920x1080 desktop")
    shot.add_argument("--preview-set", metavar="PROP=JSON", action="append", default=[],
                      help="set a property of the preview (e.g. closeUp=true)")
    shot.add_argument("--change", metavar="SETTING=JSON", action="append", default=[],
                      help="change a setting once the window is up (e.g. menuGrow=false), to catch its live effect")
    shot.add_argument("--after-change-ms", type=int, help="take the picture this long after --change")
    shot.add_argument("--size", help="content size WxH (shadow margin is added); default 1280x820, smaller on small screens")
    shot.add_argument("--delay-ms", type=int, default=2500)
    ap.add_argument("--lang", metavar="CODE", help="show the app in this language (de, es, fr, it, pt_BR, en)")
    return ap.parse_args(argv)


def _pick_font(app) -> None:
    from PySide6.QtGui import QFont, QFontDatabase
    families = set(QFontDatabase.families())
    for name in ("Adwaita Sans", "Cantarell", "Inter"):
        if name in families:
            f = QFont(name)
            f.setPixelSize(14)
            f.setHintingPreference(QFont.PreferNoHinting)
            app.setFont(f)
            return


_QML_CACHE = re.compile(r"qmlcache-[0-9][0-9A-Za-z.+~-]{0,40}")


def tidy_qml_caches(folder: Path, keep: str) -> int:
    """Each version keeps its compiled screens in its own qmlcache-<version> folder, and
    the old ones were never removed (seven of them on Dino's PC after 1.5.6). Remove
    the ones from other versions: real folders with that name only, never a link."""
    removed = 0
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return 0
    for e in entries:
        if e.name == keep or not _QML_CACHE.fullmatch(e.name):
            continue
        try:
            if e.is_symlink() or not e.is_dir(follow_symlinks=False):
                continue
            shutil.rmtree(e.path)
            removed += 1
        except OSError:
            pass    # in use or not ours to remove: leave it
    return removed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    page = PAGE_ALIASES.get(args.page, args.page)
    if args.section:
        page = PAGE_ALIASES.get(args.section, args.section)
    if page not in PAGE_IDS:
        page = "home"

    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    if "QML_DISK_CACHE_PATH" not in os.environ:
        os.environ["QML_DISK_CACHE_PATH"] = str(cache / "liquid-glass" / f"qmlcache-{__version__}")
        tidy_qml_caches(cache / "liquid-glass", f"qmlcache-{__version__}")
    # "Qt apps get the same title bar" sends Qt apps through XWayland; this app draws
    # its own glass header, so it stays on Wayland when it can.
    if os.environ.get("QT_QPA_PLATFORM") == "xcb;wayland":
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

    try:
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
        from PySide6.QtQuick import QQuickWindow  # noqa: F401 - registers the window type
        from PySide6.QtQuickControls2 import QQuickStyle
    except ImportError:
        from .. import distro
        print(f"The Fedora Glass app needs PySide6: {distro.hint('pyside6', 'install PySide6')}", file=sys.stderr)
        return 1

    from .backend import Backend
    from .cursor_picker import CursorImages, CursorPicker
    from .icons import IconProvider

    QGuiApplication.setApplicationName("Fedora Glass")
    QGuiApplication.setApplicationDisplayName("Fedora Glass")
    QGuiApplication.setOrganizationDomain("djshiye.github.io")
    QGuiApplication.setDesktopFileName(APP_ID)
    app = QGuiApplication(sys.argv[:1])
    from .. import i18n
    if args.lang:
        i18n.reset("" if args.lang.split("_")[0] == "en" else i18n.pick_language({"FEDORA_GLASS_LANG": args.lang}) or "")
    i18n.install_qt(app)
    QQuickStyle.setStyle("Basic")
    _pick_font(app)
    if not QIcon.themeName():
        QIcon.setThemeName("Adwaita")
    QIcon.setFallbackThemeName("hicolor")

    icon_path = find_icon()
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))

    forced = None if args.scheme is None else args.scheme == "dark"
    # Register the backend before the engine exists: types registered later
    # can leave already-loaded plugin types (QtQuick.Shapes) half-resolved.
    backend = Backend(ui_dark=forced, parent=app)
    if forced is not None:
        backend.previewDark = forced
    if args.frost is not None:
        backend.frost = args.frost

    qmlRegisterSingletonInstance(Backend, "FedoraGlass.Core", 1, 0, "Backend", backend)
    cursor_picker = CursorPicker(backend._env, parent=app)
    qmlRegisterSingletonInstance(CursorPicker, "FedoraGlass.Core", 1, 0, "Cursors", cursor_picker)
    engine = QQmlApplicationEngine()
    engine.setUiLanguage(i18n.language() or "en")
    engine.addImageProvider("lgicon", IconProvider())
    engine.addImageProvider("lgcursor", CursorImages(backend._env))
    engine.addImportPath(str(QML_DIR))
    engine.rootContext().setContextProperty(
        "appIconUrl", QUrl.fromLocalFile(str(icon_path)) if icon_path else QUrl())
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        return 1
    win = engine.rootObjects()[0]

    margin = int(win.property("margin") or 0)
    if args.size:
        w, h = (int(v) for v in args.size.lower().split("x"))
    else:
        w, h = fit_size(win.screen().availableGeometry() if win.screen() else None, margin)
    win.setWidth(w + 2 * margin)
    win.setHeight(h + 2 * margin)
    win.setProperty("page", page)
    if args.fine_tune:
        page = "advanced"
        win.setProperty("page", page)
        win.setProperty("fineTuneOpen", True)
    win.show()
    # First launch: a short welcome. Screenshots ask for it with --sheet welcome.
    if backend.firstRun and not args.screenshot:
        win.setProperty("startSheet", "welcome")

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app.aboutToQuit.connect(backend.shutdown)

    if args.screenshot:
        out = args.screenshot

        def stage() -> None:
            if args.held:
                from PySide6.QtCore import QObject
                home = win.findChild(QObject, "homePage")
                if home is not None:
                    home.setProperty("frostHeld", 1.0)
            if args.preview_set:
                import json
                from PySide6.QtCore import QObject
                pv = win.findChild(QObject, "preview")
                for kv in args.preview_set:
                    k, _, v = kv.partition("=")
                    if pv is not None:
                        pv.setProperty(k, json.loads(v))
            if args.change:
                import json
                for kv in args.change:
                    k, _, v = kv.partition("=")
                    backend.setProperty(k, json.loads(v))
                if args.after_change_ms is not None:
                    QTimer.singleShot(args.after_change_ms, grab)
            if args.preview_scene or args.preview_pointer:
                from PySide6.QtCore import QObject
                pv = win.findChild(QObject, "preview")
                if pv is not None and args.preview_scene:
                    pv.setProperty("scene", args.preview_scene)
                if pv is not None and args.preview_pointer:
                    k = pv.property("width") / 1920
                    x, y = (float(v) * k for v in args.preview_pointer.split(","))
                    pv.setProperty("demoX", x)
                    pv.setProperty("demoY", y)
                    pv.setProperty("pointerPinned", True)
            if args.scroll:
                from PySide6.QtCore import QObject
                side = win.findChild(QObject, {"apps": "appsList"}.get(page, page + "Scroller"))
                if side is not None:
                    side.setProperty("contentY", args.scroll)
            if args.reveal:
                from PySide6.QtCore import Q_ARG, QMetaObject
                ok = QMetaObject.invokeMethod(win, "goTo", Q_ARG("QVariant", page), Q_ARG("QVariant", args.reveal))
                print(f"reveal {args.reveal}: {ok}", flush=True)
            if args.lock_preview:
                from PySide6.QtCore import QObject
                lp = win.findChild(QObject, "lockPage")
                if lp is not None:
                    lp.setProperty("previewMode", args.lock_preview)
            if args.sheet == "changes":
                backend.requestPlan()
            elif args.sheet == "results":
                backend.applyFinished.emit(_demo_results(backend))
            elif args.sheet == "restore":
                win.setProperty("startSheet", "restore")
            elif args.sheet == "welcome":
                win.setProperty("startSheet", "welcome")
            elif args.sheet == "leave":
                win.close()     # with unapplied changes (--change) this asks first
            elif args.sheet == "about":
                from PySide6.QtCore import QMetaObject, QObject
                QMetaObject.invokeMethod(win.findChild(QObject, "aboutSheet"), "open")
            if args.dropdown or args.tip:
                from PySide6.QtCore import QMetaObject, QObject

                def find(name):
                    # Repeater rows are only visual children: walk the item tree too.
                    hit = win.findChild(QObject, name)
                    todo = [win.contentItem()]
                    while hit is None and todo:
                        it = todo.pop()
                        if it.objectName() == name:
                            hit = it
                        todo.extend(it.childItems())
                    return hit
                if args.dropdown:
                    dd = find(args.dropdown)
                    if dd is not None:
                        dd.setProperty("focus", True)
                        ok = QMetaObject.invokeMethod(dd, "open")
                        print(f"dropdown {args.dropdown}: {'opened' if dd.property('opened') else 'not opened'} ({ok})", flush=True)
                if args.tip:
                    ctl = find(args.tip)
                    tips = [] if ctl is None else [c for c in ctl.findChildren(QObject)
                                                   if c.metaObject().indexOfProperty("shown") >= 0]
                    if tips:
                        tips[0].setProperty("delay", 0)
                        tips[0].setProperty("shown", True)

        def grab() -> None:
            img = win.grabWindow()
            ok = img.save(out)
            print(f"screenshot {'saved' if ok else 'FAILED'}: {out} {img.width()}x{img.height()}", flush=True)
            app.exit(0 if ok else 2)
        QTimer.singleShot(max(200, args.delay_ms // 2), stage)
        if not (args.change and args.after_change_ms is not None):
            QTimer.singleShot(args.delay_ms, grab)

    return app.exec()


def fit_size(avail, margin: int) -> tuple[int, int]:
    """The window's first size: 1280x820, or less so it fits the screen.

    On Wayland Qt can't see GNOME's top bar or Dash to Panel, so room is left for
    them. Never below the window's minimum (1000x600, which fits 1280x720).
    """
    w, h = 1280, 820
    if avail is not None and avail.width() > 0 and avail.height() > 0:
        w = min(w, avail.width() - 2 * margin - 48)
        h = min(h, avail.height() - 2 * margin - 112)
    return max(1000, w), max(600, h)


def _demo_results(backend) -> list[dict]:
    """Results for the screenshot of the results sheet, built from the real targets."""
    out = []
    for g in backend.targets:
        for t in g["items"]:
            if not t["enabled"]:
                continue
            if t["available"]:
                out.append({"id": t["id"], "name": t["name"], "status": "applied", "message": ""})
            else:
                out.append({"id": t["id"], "name": t["name"], "status": "skipped", "message": t["detail"]})
    return out


if __name__ == "__main__":
    sys.exit(main())
