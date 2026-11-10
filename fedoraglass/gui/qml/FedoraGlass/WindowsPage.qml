import QtQuick
import FedoraGlass.Core

// Panel and windows: Dash to Panel's shape, window header bars, and (folded) the
// terminal and Qt apps.
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
            SectionTitle { text: "Panel"; resetKeys: ["panel_style", "panel_margin"] }
            Column {
                width: parent.width
                spacing: 8
                Text { text: "Dash to Panel"; color: Theme.text; font.pixelSize: Theme.fsBody; font.weight: Font.Medium }
                Segmented {
                    objectName: "panelStyle"
                    width: parent.width
                    model: [{ value: "floating", label: "Floating", icon: "panelFloat", tip: "A glass pill that floats above the screen edge" },
                            { value: "docked", label: "Docked", icon: "panelDock", tip: "A full-width bar along the screen edge" }]
                    value: Backend.panelStyle
                    onActivated: (v) => Backend.panelStyle = v
                    Accessible.name: "Panel style"
                }
            }
            LabeledSlider {
                objectName: "panelMargin"
                label: "Panel margin"
                enabled: Backend.panelStyle === "floating"
                from: 0; to: 32; stepSize: 1
                value: Backend.panelMargin
                defaultValue: Backend.defaults.panel_margin
                format: (v) => Math.round(v) + " px"
                onMoved: (v) => Backend.panelMargin = v
                tip: "The gap between the floating panel and the screen edge. Left sits it against the edge; right floats it further away."
            }
        }
    }

    HeaderBarCard { width: parent.width }

    side: [
        Item { id: slot; objectName: "windowsPreviewSlot"; width: parent.width; height: Math.round(width * 9 / 16) },
        PreviewNote {}
    ]
}
