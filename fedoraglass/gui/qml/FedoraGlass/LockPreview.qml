import QtQuick
import QtQuick.Effects
import FedoraGlass.Core

// A miniature of the lock screen as the Shell extension draws it (lock.js and
// lockwidgets.js): the frosted sheet over the real wallpaper, GNOME's clock in the
// chosen cut and place, the widgets under it, and the password card. Laid out on a
// virtual 1920x1080 screen and scaled by `s`, like the desktop preview.
Item {
    id: root

    property string wallpaper: Backend.wallpaper
    property string mode: "rest"         // rest: the clock; prompt: typing the password
    property real slide: 0               // 0 locked .. 1 slid away (the unlock animation)
    readonly property bool resting: mode === "rest"

    readonly property real s: width / 1920
    function u(n) { return n * root.s }
    function pt(n) { return n * 4 / 3 * root.s }      // St's pt at 96 dpi, on the virtual screen

    // ---- what the extension does with the settings -------------------------------
    readonly property bool glass: Backend.lockGlass && !Backend.reduceTransparency
    readonly property real blurPx: (glass ? Backend.lockBlur : 45) * s
    // The sheet's brightness (render/glass.py: dim = 1 - lock_dim), then the ceiling that
    // keeps the white clock readable: linear Y at most 0.13 (lock.js SHEET_CEILING).
    readonly property real sheetBright: glass ? 1 - Backend.lockDim : 0.65
    readonly property real ceilingFactor: glass ? Math.min(1, 0.13 / Math.max(0.001, Backend.wallpaperLuma * sheetBright)) : 1
    // A black veil darkens sRGB values; the factor above is linear light.
    readonly property real veil: 1 - Math.pow(sheetBright * ceilingFactor, 1 / 2.2)
    readonly property color tint: Backend.tint
    readonly property real tintAlpha: glass ? Backend.lockTint * 0.4 : 0

    // Only the glass restyles and moves GNOME's clock (lock.js).
    readonly property string clockStyle: glass ? Backend.lockClock : "gnome"
    readonly property string clockPosition: glass ? Backend.lockClockPosition : "gnome"
    readonly property var clockLook: ({
        gnome: { time: 64, timeW: Font.ExtraBold, date: 16, dateW: Font.Normal },
        bold:  { time: 96, timeW: Font.ExtraBold, date: 16, dateW: Font.DemiBold },
        thin:  { time: 92, timeW: Font.ExtraLight, date: 16, dateW: Font.Normal }
    })[clockStyle] ?? { time: 64, timeW: Font.ExtraBold, date: 16, dateW: Font.Normal }

    readonly property bool chips: Backend.lockWidgetStyle !== "plain"
    readonly property bool showBattery: Backend.lockWidgetBattery && Backend.hasBattery
    readonly property bool showWeather: Backend.lockWidgetWeather && Backend.weatherState === "ready"
    readonly property bool showMessage: Backend.lockMessage.length > 0
    readonly property bool showNotifications: !Backend.lockHideNotifications

    property date now: new Date()
    Timer { interval: 30000; running: root.visible; repeat: true; onTriggered: root.now = new Date() }
    function greeting() {
        const h = now.getHours()
        return h >= 5 && h < 12 ? "Good morning" : h >= 12 && h < 17 ? "Good afternoon"
             : h >= 17 && h < 22 ? "Good evening" : "Good night"
    }

    clip: true

    // ---- the desktop the sheet slides away from ------------------------------------
    Image {
        id: wall
        anchors.fill: parent
        source: root.wallpaper
        sourceSize.width: 960
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
    }
    Rectangle { anchors.fill: parent; color: "#1b1c22"; visible: wall.status !== Image.Ready; z: -1 }

    // ---- the lock screen ----------------------------------------------------------
    Item {
        id: lock
        width: parent.width
        height: parent.height
        y: -root.slide * parent.height
        visible: root.slide < 1

        MultiEffect {
            anchors.fill: parent
            source: wall
            visible: wall.status === Image.Ready
            blurEnabled: true
            blurMax: 64
            blur: Math.min(1, root.blurPx / 64)
            saturation: root.glass ? 0.35 : 0
            autoPaddingEnabled: false
        }
        Rectangle { anchors.fill: parent; color: "black"; opacity: root.veil }
        Rectangle { anchors.fill: parent; color: root.tint; opacity: root.tintAlpha }
        // The moving sheet's lower edge is glass: a thin bright line while it slides.
        Rectangle {
            visible: root.slide > 0 && root.glass
            anchors.bottom: parent.bottom
            width: parent.width; height: Math.max(1, root.u(2))
            color: Qt.rgba(1, 1, 1, 0.35)
        }

        // Top bar of the lock screen: GNOME's own, only the status icons.
        Row {
            anchors.right: parent.right
            anchors.rightMargin: root.u(24)
            y: root.u(10)
            spacing: root.u(16)
            Repeater {
                model: ["wifi", "volume", "power"]
                delegate: Icon {
                    required property string modelData
                    name: modelData
                    size: root.u(22)
                    color: "white"
                    layered: false
                }
            }
        }

        // ---- the clock column (GNOME's stack: clock, or the password prompt) ----------
        Column {
            id: clock
            objectName: "lockPreviewClock"
            width: parent.width
            spacing: root.u(24)
            opacity: root.resting ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
            // Where GNOME puts it (a third of the way down), or where the setting moves it.
            y: root.clockPosition === "top" ? root.u(76)
             : root.clockPosition === "middle" ? (root.height - height) / 2
             : Math.min(root.height / 3, root.height - height - notes.height)
            Behavior on y { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }

            Text {
                visible: Backend.lockGreeting
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.greeting()
                color: "white"
                font.pixelSize: root.pt(17)
                font.weight: Font.Medium
                bottomPadding: -root.u(20)
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                topPadding: Backend.lockGreeting ? 0 : root.u(42)
                text: Qt.formatTime(root.now, Qt.locale().timeFormat(Locale.ShortFormat).indexOf("AP") >= 0 ? "h:mm" : "HH:mm")
                color: "white"
                font.pixelSize: root.pt(root.clockLook.time)
                font.weight: root.clockLook.timeW
                font.features: { "tnum": 1 }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Qt.formatDate(root.now, "dddd MMMM d")
                color: "white"
                font.pixelSize: root.pt(root.clockLook.date)
                font.weight: root.clockLook.dateW
            }

            // The widgets, under the date (lockwidgets.js).
            Column {
                objectName: "lockPreviewWidgets"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: row.visibleChildren.length > 1 || root.showMessage
                spacing: root.u(root.chips ? 12 : 10)
                topPadding: root.u(root.chips ? 22 - 24 : 18 - 24)
                Row {
                    id: row
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: root.u(root.chips ? 10 : 22)
                    Chip_ { visible: root.showBattery; icon: "battery"; text: "82%" }
                    Chip_ {
                        visible: root.showWeather
                        icon: "cloud"
                        text: "14°  ·  Partly cloudy" + (Backend.lockWeatherPlace ? "  ·  Your town" : "")
                    }
                }
                Rectangle {
                    visible: root.showMessage
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(msg.implicitWidth, root.u(520)) + (root.chips ? root.u(34) : 0)
                    height: msg.height + (root.chips ? root.u(20) : root.u(4))
                    radius: root.u(16)
                    color: root.chips ? Qt.rgba(1, 1, 1, 0.09) : "transparent"
                    border.width: root.chips ? Math.max(1, root.u(1)) : 0
                    border.color: Qt.rgba(1, 1, 1, 0.16)
                    Text {
                        id: msg
                        anchors.centerIn: parent
                        width: Math.min(implicitWidth, root.u(520))
                        text: Backend.lockMessage
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                        color: "white"
                        font.pixelSize: root.pt(11.5)
                        font.weight: Font.Medium
                    }
                }
            }
            Text {   // GNOME's hint, faded in after a while
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Click or press a key to unlock"
                color: Qt.rgba(1, 1, 1, 0.7)
                font.pixelSize: root.pt(11)
                topPadding: root.u(24)
            }
        }

        // GNOME's notifications and music controls, at the bottom of the column.
        Rectangle {
            id: notes
            visible: root.showNotifications && root.resting
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.height - height - root.u(36)
            width: root.u(480)
            height: visible ? root.u(64) : 0
            radius: root.u(16)
            color: Qt.rgba(1, 1, 1, 0.1)
            Row {
                anchors.left: parent.left
                anchors.leftMargin: root.u(18)
                anchors.verticalCenter: parent.verticalCenter
                spacing: root.u(14)
                Icon { name: "message"; size: root.u(28); color: "white"; layered: false; anchors.verticalCenter: parent.verticalCenter }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    Text { text: "Messages"; color: "white"; font.pixelSize: root.pt(11); font.weight: Font.Bold }
                    Text { text: "2 new notifications"; color: Qt.rgba(1, 1, 1, 0.75); font.pixelSize: root.pt(10) }
                }
            }
        }

        // ---- the password prompt, on its glass card --------------------------------
        Item {
            id: prompt
            objectName: "lockPreviewPrompt"
            width: root.u(360)
            height: promptCol.height
            anchors.horizontalCenter: parent.horizontalCenter
            y: (root.clockPosition === "top" ? root.u(76)
               : root.clockPosition === "middle" ? (root.height - height) / 2
               : root.height / 3) + (root.resting ? root.u(16) : 0)
            opacity: root.resting ? 0 : 1
            visible: opacity > 0
            scale: root.resting ? 0.9 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
            Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
            Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }

            // The card (lock.js cardLook: a little lighter, a rim, 28 px of glass around).
            Rectangle {
                visible: root.glass && Backend.lockCard
                x: -root.u(28); y: -root.u(28)
                width: parent.width + root.u(56); height: parent.height + root.u(56)
                radius: Math.min(root.u(32), height / 2)
                color: Qt.rgba(1, 1, 1, 0.08)
                border.width: Math.max(1, root.u(1.2))
                border.color: Qt.rgba(1, 1, 1, 0.2)
                Rectangle {   // the bright top rim
                    x: parent.radius; width: parent.width - 2 * parent.radius
                    y: 0; height: Math.max(1, root.u(1.5))
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "transparent" }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.45) }
                        GradientStop { position: 1; color: "transparent" }
                    }
                }
            }
            Column {
                id: promptCol
                width: parent.width
                spacing: root.u(18)
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: root.u(128); height: width; radius: width / 2
                    color: Qt.rgba(1, 1, 1, 0.16)
                    Icon { anchors.centerIn: parent; name: "user"; size: root.u(64); color: "white"; layered: false }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: Backend.userName || "You"
                    color: "white"
                    font.pixelSize: root.pt(14)
                    font.weight: Font.Bold
                }
                Rectangle {
                    width: parent.width; height: root.u(48); radius: root.u(12)
                    color: Qt.rgba(1, 1, 1, 0.13)
                    border.width: Math.max(1, root.u(2))
                    border.color: Theme.accent
                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: root.u(16)
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: root.u(7)
                        Repeater {
                            model: 6
                            delegate: Rectangle { width: root.u(9); height: width; radius: width / 2; color: "white" }
                        }
                    }
                }
            }
        }
    }

    // A widget chip: a small pane of glass, or plain text (lockwidgets.js STYLES).
    component Chip_: Rectangle {
        property string icon: ""
        property string text: ""
        width: chipRow.width + (root.chips ? root.u(29) : 0)
        height: chipRow.height + (root.chips ? root.u(14) : root.u(4))
        radius: height / 2
        color: root.chips ? Qt.rgba(1, 1, 1, 0.11) : "transparent"
        border.width: root.chips ? Math.max(1, root.u(1)) : 0
        border.color: Qt.rgba(1, 1, 1, 0.17)
        Rectangle {   // brighter top rim
            visible: root.chips
            x: parent.radius; width: parent.width - 2 * parent.radius
            y: 0; height: Math.max(1, root.u(1))
            color: Qt.rgba(1, 1, 1, 0.3)
        }
        Row {
            id: chipRow
            x: root.chips ? root.u(13) : 0
            anchors.verticalCenter: parent.verticalCenter
            spacing: root.u(8)
            Icon { name: parent.parent.icon; size: root.u(18); strokeWidth: 2; color: "white"; layered: false; anchors.verticalCenter: parent.verticalCenter }
            Text {
                text: parent.parent.text
                color: "white"
                font.pixelSize: root.pt(11.5)
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
