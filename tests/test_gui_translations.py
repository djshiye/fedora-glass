"""The app's words reach QML: qsTr() finds the po translation, a context picks the right
one, and a word with no translation stays English (never empty)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = r'''
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from fedoraglass import i18n
app = QGuiApplication([])
i18n.reset(sys.argv[2])
i18n.install_qt(app)
qml = sys.argv[3] + "/t.qml"
open(qml, "w").write("""import QtQuick
Item { Component.onCompleted: {
    console.info("RESULT|" + [qsTr("Apply"), qsTr("Home"), qsTr("Home", "folder"),
                 qsTr("No such words %1").arg(7), qsTr("Clear", "preset")].join("|")); Qt.quit() } }""")
e = QQmlApplicationEngine()
e.load(QUrl.fromLocalFile(qml))
app.exec()
'''


def run(lang, tmp_path):
    pytest.importorskip("PySide6.QtQml")
    out = subprocess.run([sys.executable, "-c", SCRIPT, str(ROOT), lang, str(tmp_path)],
                         capture_output=True, text=True, timeout=60)
    line = next((l for l in (out.stdout + out.stderr).splitlines() if "RESULT|" in l), "")
    assert line, out.stdout + out.stderr
    return line.split("RESULT|", 1)[1].split("|")


def test_german_words_reach_qml(tmp_path):
    apply_, home, folder, missing, clear = run("de", tmp_path)
    assert apply_ == "Anwenden"
    assert home == "Start" and folder == "Persönlicher Ordner"
    assert missing == "No such words 7"
    assert clear == "Klar"


def test_english_stays_english(tmp_path):
    assert run("", tmp_path) == ["Apply", "Home", "Home", "No such words 7", "Clear"]
