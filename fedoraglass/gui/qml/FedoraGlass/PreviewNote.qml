import QtQuick
import FedoraGlass.Core

// The line under a page's preview: what it shows, and when the desktop changes.
Text {
    width: parent ? parent.width : 300
    leftPadding: 4; rightPadding: 4
    text: Backend.glassPaused
          ? qsTr("The preview changes as you move things. Glass is paused, so your desktop shows what you apply once you resume it.")
          : qsTr("The preview changes as you move things. Your desktop changes when you press Apply.")
    wrapMode: Text.WordWrap
    color: Theme.textFaint
    font.pixelSize: Theme.fsSmall + 1
}
