import QtQuick
import FedoraGlass.Core

SettingsPage {
    id: page
    objectName: "pointerPage"
    pageId: "pointer"
    previewSlot: slot
    Card { width: parent.width; height: 200 }
    side: [ Item { id: slot; width: parent.width; height: width * 9 / 16 } ]
}
