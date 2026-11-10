import QtQuick
import FedoraGlass.Core

// Pointer and desktop: the mouse pointer style and size, and how the desktop starts.
SettingsPage {
    id: page
    objectName: "pointerPage"
    pageId: "pointer"
    previewSlot: slot

    CursorCard { width: parent.width }

    Card {
        width: parent.width
        height: implicitHeight
        Column {
            width: parent.width
            spacing: 4
            SectionTitle { text: "Desktop"; resetKeys: ["start_on_desktop", "overview_off"] }
            SwitchRow {
                objectName: "startOnDesktop"
                label: "Start on the desktop"
                caption: "Start straight on your desktop, not the Activities overview"
                tip: "When your PC starts, GNOME shows your desktop and panel instead of opening Activities first. Until you choose, it is on with Dash to Panel and off on GNOME's own desktop. If Dash to Panel or Just Perfection is installed, their own start-up option is set to match."
                enabled: !Backend.overviewOff
                // Not chosen yet, it follows the desktop (on with Dash to Panel), which is
                // known once the installed extensions are: read hasDashToPanel to follow it.
                checked: (Backend.hasDashToPanel, Backend.startOnDesktop) || Backend.overviewOff
                onToggled: (on) => Backend.startOnDesktop = on
            }
            SwitchRow {
                objectName: "overviewOff"
                label: "Turn off the overview"
                caption: "No overview from the Super key, hot corner or swipe, and no workspace view"
                tip: "What stops working: the Super key no longer opens the overview, the top-left hot corner does nothing, and the workspace and window overview is gone. "
                     + (Backend.hasStartMenu ? "Open apps from ArcMenu, Spawn, Dash to Panel or a dock. "
                                             : "Without ArcMenu or Spawn the app grid still opens, so you can open apps from it, Dash to Panel or a dock. ")
                     + "Switch this off, or turn off Fedora Glass, and it all comes back at once."
                checked: Backend.overviewOff
                onToggled: (on) => { Backend.overviewOff = on; if (Theme.preview) Theme.preview.scene = "overview" }
            }
        }
    }

    side: [
        Item { id: slot; objectName: "pointerPreviewSlot"; width: parent.width; height: page.previewH },
        PreviewNote {}
    ]
}
