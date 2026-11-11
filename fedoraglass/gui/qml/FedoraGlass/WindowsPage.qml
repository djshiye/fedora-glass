import QtQuick
import FedoraGlass.Core

// Panel and windows: Dash to Panel's shape, window header bars, (folded) the terminal and
// Qt apps, and the apps whose windows get no glass.
SettingsPage {
    id: page
    objectName: "windowsPage"
    pageId: "windows"
    previewSlot: slot

    Card {
        // Floating or docked, and the margin, are Dash to Panel's: on GNOME's own top bar
        // or a dock they would change nothing.
        visible: Backend.hasDashToPanel
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 16
            SectionTitle { text: qsTr("Panel"); resetKeys: ["panel_style", "panel_margin"] }
            Column {
                width: parent.width
                spacing: 8
                Text { text: qsTr("Dash to Panel"); color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                Segmented {
                    objectName: "panelStyle"
                    width: parent.width
                    model: [{ value: "floating", label: qsTr("Floating"), icon: "panelFloat", tip: qsTr("A glass pill that floats above the screen edge") },
                            { value: "docked", label: qsTr("Docked"), icon: "panelDock", tip: qsTr("A full-width bar along the screen edge") }]
                    value: Backend.panelStyle
                    onActivated: (v) => Backend.panelStyle = v
                    Accessible.name: qsTr("Panel style")
                }
            }
            LabeledSlider {
                objectName: "panelMargin"
                label: qsTr("Panel margin")
                enabled: Backend.panelStyle === "floating"
                from: 0; to: 32; stepSize: 1
                value: Backend.panelMargin
                defaultValue: Backend.defaults.panel_margin
                format: (v) => qsTr("%1 px").arg(Math.round(v))
                onMoved: (v) => Backend.panelMargin = v
                tip: qsTr("The gap between the floating panel and the screen edge. Left sits it against the edge; right floats it further away.")
            }
        }
    }

    HeaderBarCard { width: parent.width }

    NoGlassCard { width: parent.width }

    side: [
        Item { id: slot; objectName: "windowsPreviewSlot"; width: parent.width; height: page.previewH },
        PreviewNote {}
    ]
}
