import QtQuick
import FedoraGlass.Core

SettingsPage {
    id: page
    objectName: "aboutPage"
    pageId: "about"
    previewSlot: slot
    Card { width: parent.width; height: 200 }
    side: [ Item { id: slot; width: parent.width; height: width * 9 / 16 } ]
}
