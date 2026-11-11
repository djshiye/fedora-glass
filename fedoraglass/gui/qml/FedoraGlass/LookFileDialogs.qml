import QtQuick
import QtQuick.Dialogs as D
import FedoraGlass.Core

// The file dialogs for saved looks: add one from a file, save one as a file. They start in
// Documents (or the home folder). Kept apart from SavedLooks, which loads this only when
// asked, since QtQuick.Dialogs is a package of its own on some systems.
Item {
    id: root
    signal importPicked(url file)
    signal exportPicked(string lookId, url file)
    function openImport() { importDialog.open() }
    function openExport(lookId) {
        exportDialog.lookId = lookId
        exportDialog.selectedFile = Backend.looksFolder + "/" + Backend.lookFileName(lookId)
        exportDialog.open()
    }
    D.FileDialog {
        id: importDialog
        title: qsTr("Add a look from a file")
        fileMode: D.FileDialog.OpenFile
        currentFolder: Backend.looksFolder
        nameFilters: [qsTr("Fedora Glass looks (*.json)"), qsTr("All files (*)")]
        onAccepted: root.importPicked(selectedFile)
    }
    D.FileDialog {
        id: exportDialog
        property string lookId: ""
        title: qsTr("Save the look as a file")
        fileMode: D.FileDialog.SaveFile
        currentFolder: Backend.looksFolder
        defaultSuffix: "json"
        nameFilters: [qsTr("Fedora Glass looks (*.json)")]
        onAccepted: root.exportPicked(lookId, selectedFile)
    }
}
