"""Liquid Glass customizer: a Qt Quick window over the engine.

`python3 -m liquidglass gui` lands here. `--screenshot PATH` renders the
window to a PNG once it has settled (for docs and tests) and quits.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

from .. import APP_ID, __version__

HERE = Path(__file__).resolve().parent
QML_DIR = HERE / "qml"
PAGES = {"look": 0, "apps": 1}


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
    ap = argparse.ArgumentParser(prog="liquid-glass gui", description="Liquid Glass customizer")
    shot = ap.add_argument_group("screenshots")
    shot.add_argument("--screenshot", metavar="PATH", help="render the window to a PNG, then quit")
    shot.add_argument("--page", default="0", help="page to show: 0/look or 1/apps")
    shot.add_argument("--frost", type=float, help="set the frost slider (0..1) without saving")
    shot.add_argument("--scheme", choices=("dark", "light"), help="force the app and preview style")
    shot.add_argument("--held", action="store_true", help="draw the frost knob as if it were being dragged")
    shot.add_argument("--fine-tune", action="store_true", help="open the Fine-tune section")
    shot.add_argument("--scroll", type=float, default=0, help="scroll the options column down this far, in px")
    shot.add_argument("--sheet", choices=("changes", "results", "restore"), help="open a sheet")
    shot.add_argument("--dropdown", metavar="NAME", help="open the dropdown with this objectName")
    shot.add_argument("--tip", metavar="NAME", help="show the tooltip of the control with this objectName")
    shot.add_argument("--size", default="1280x820", help="content size WxH (shadow margin is added)")
    shot.add_argument("--delay-ms", type=int, default=2500)
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    page = PAGES.get(args.page, None)
    if page is None:
        try:
            page = max(0, min(1, int(args.page)))
        except ValueError:
            page = 0

    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    os.environ.setdefault("QML_DISK_CACHE_PATH", str(cache / "liquid-glass" / f"qmlcache-{__version__}"))

    try:
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
        from PySide6.QtQuick import QQuickWindow  # noqa: F401 - registers the window type
        from PySide6.QtQuickControls2 import QQuickStyle
    except ImportError:
        print("The Liquid Glass app needs PySide6: sudo dnf install python3-pyside6", file=sys.stderr)
        return 1

    from .backend import Backend
    from .icons import IconProvider

    QGuiApplication.setApplicationName("Liquid Glass")
    QGuiApplication.setApplicationDisplayName("Liquid Glass")
    QGuiApplication.setOrganizationDomain("djshiye.github.io")
    QGuiApplication.setDesktopFileName(APP_ID)
    app = QGuiApplication(sys.argv[:1])
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

    qmlRegisterSingletonInstance(Backend, "LiquidGlass.Core", 1, 0, "Backend", backend)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("lgicon", IconProvider())
    engine.addImportPath(str(QML_DIR))
    engine.rootContext().setContextProperty(
        "appIconUrl", QUrl.fromLocalFile(str(icon_path)) if icon_path else QUrl())
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        return 1
    win = engine.rootObjects()[0]

    w, h = (int(v) for v in args.size.lower().split("x"))
    margin = int(win.property("margin") or 0)
    win.setWidth(w + 2 * margin)
    win.setHeight(h + 2 * margin)
    win.setProperty("pageIndex", page)
    if args.fine_tune:
        win.setProperty("fineTuneOpen", True)
    win.show()

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app.aboutToQuit.connect(backend.shutdown)

    if args.screenshot:
        out = args.screenshot

        def stage() -> None:
            if args.held:
                win.setProperty("frostHeld", 1.0)
            if args.scroll:
                from PySide6.QtCore import QObject
                side = win.findChild(QObject, "options")
                if side is not None:
                    side.setProperty("contentY", args.scroll)
            if args.sheet == "changes":
                backend.requestPlan()
            elif args.sheet == "results":
                backend.applyFinished.emit(_demo_results(backend))
            elif args.sheet == "restore":
                win.setProperty("startSheet", "restore")
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
        QTimer.singleShot(args.delay_ms, grab)

    return app.exec()


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
