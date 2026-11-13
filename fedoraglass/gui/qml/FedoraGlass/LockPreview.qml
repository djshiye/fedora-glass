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
    property string screen: "lock"       // lock, or login: the glass login screen (GDM)
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
        return h >= 5 && h < 12 ? qsTr("Good morning") : h >= 12 && h < 17 ? qsTr("Good afternoon")
             : h >= 17 && h < 22 ? qsTr("Good evening") : qsTr("Good night")
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
        visible: root.slide < 1 && root.screen === "lock"

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
                        text: Backend.lockWeatherPlace ? qsTr("14°  ·  Partly cloudy  ·  Your town") : qsTr("14°  ·  Partly cloudy")
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
                text: qsTr("Click or press a key to unlock")
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
                    Text { text: qsTr("Messages"); color: "white"; font.pixelSize: root.pt(11); font.weight: Font.Bold }
                    Text { text: qsTr("2 new notifications"); color: Qt.rgba(1, 1, 1, 0.75); font.pixelSize: root.pt(10) }
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
                    text: Backend.userName || qsTr("You")
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

    // ---- the glass login screen ------------------------------------------------------
    // What the login add-on draws from the values the app sends (Backend.glassLoginLook,
    // the editor's, so it follows the sliders): the picture, the frosted sheet over it, the
    // big clock at the top (the user list needs the middle), and the password on its card.
    Item {
        id: login
        objectName: "loginPreview"
        anchors.fill: parent
        visible: root.screen === "login"
        readonly property var look: Backend.glassLoginLook
        readonly property string picture: look.picture || "wallpaper"
        readonly property real sheetBright: 1 - (look.dim ?? 0.28)
        // The same brightness ceiling as the lock screen keeps the white text readable.
        readonly property real luma: picture === "wallpaper" ? Backend.wallpaperLuma : picture === "glow" ? 0.08 : 0.03
        readonly property real ceiling: Math.min(1, 0.13 / Math.max(0.001, luma * sheetBright))
        readonly property real veil: 1 - Math.pow(sheetBright * ceiling, 1 / 2.2)
        readonly property var clock: ({
            bold: { time: 96, timeW: Font.ExtraBold, dateW: Font.DemiBold },
            thin: { time: 92, timeW: Font.ExtraLight, dateW: Font.Normal }
        })[look.clock] ?? null
        readonly property bool showBattery: look.battery === true && Backend.hasBattery
        readonly property bool showMessage: (look.message || "").length > 0

        Rectangle { anchors.fill: parent; color: "#16161b" }
        // The picture under the glass.
        Image {
            id: loginWall
            anchors.fill: parent
            visible: false
            source: login.visible && login.picture === "wallpaper" ? Backend.loginWallpaper : ""
            sourceSize.width: 960
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
        Rectangle {
            // GDM's own background, as it is without Fedora Glass: a plain dark grey.
            id: systemPic
            anchors.fill: parent
            visible: false
            gradient: Gradient {
                GradientStop { position: 0; color: "#303036" }
                GradientStop { position: 1; color: "#1e1e23" }
            }
        }
        Item {
            // The glow: soft light in the tint and accent colours.
            id: glowPic
            anchors.fill: parent
            visible: false
            Rectangle { anchors.fill: parent; color: "#121218" }
            Rectangle {
                x: parent.width * 0.05; y: -parent.height * 0.2
                width: parent.width * 0.6; height: width; radius: width / 2
                color: Qt.lighter(Backend.tint, 1.9); opacity: 0.55
            }
            Rectangle {
                x: parent.width * 0.5; y: parent.height * 0.35
                width: parent.width * 0.55; height: width; radius: width / 2
                color: Theme.accent; opacity: 0.35
            }
        }
        MultiEffect {
            anchors.fill: parent
            source: login.picture === "wallpaper" ? loginWall : login.picture === "glow" ? glowPic : systemPic
            visible: login.picture !== "wallpaper" || loginWall.status === Image.Ready
            blurEnabled: true
            blurMax: 64
            blur: login.picture === "glow" ? 1 : Math.min(1, (login.look.blur ?? 60) * root.s / 64)
            saturation: login.picture === "wallpaper" ? 0.35 : 0
            autoPaddingEnabled: false
        }
        Rectangle { anchors.fill: parent; color: "black"; opacity: login.veil }
        Rectangle { anchors.fill: parent; color: Backend.tint; opacity: (login.look.tint_amount ?? 0.2) * 0.4 }

        // GNOME's top bar on the login screen: its small clock, and the status icons.
        Text {
            objectName: "loginPreviewPanelClock"
            visible: login.clock === null
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.u(8)
            text: Qt.formatDateTime(root.now, "ddd d MMM  " + (Qt.locale().timeFormat(Locale.ShortFormat).indexOf("AP") >= 0 ? "h:mm AP" : "HH:mm"))
            color: "white"
            font.pixelSize: root.pt(11)
            font.weight: Font.Bold
        }
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

        // The big clock, at the top, and what goes under it.
        Column {
            objectName: "loginPreviewClock"
            anchors.horizontalCenter: parent.horizontalCenter
            // Under the floating Lock | Login switch, however small the preview is.
            y: Math.max(root.u(login.clock ? 70 : 64), 56)
            spacing: root.u(14)
            Text {
                visible: login.clock !== null
                anchors.horizontalCenter: parent.horizontalCenter
                text: Qt.formatTime(root.now, Qt.locale().timeFormat(Locale.ShortFormat).indexOf("AP") >= 0 ? "h:mm" : "HH:mm")
                color: "white"
                font.pixelSize: root.pt(login.clock ? login.clock.time : 64)
                font.weight: login.clock ? login.clock.timeW : Font.ExtraBold
                font.features: { "tnum": 1 }
            }
            Text {
                visible: login.clock !== null
                anchors.horizontalCenter: parent.horizontalCenter
                topPadding: -root.u(14)
                text: Qt.formatDate(root.now, "dddd MMMM d")
                color: "white"
                font.pixelSize: root.pt(16)
                font.weight: login.clock ? login.clock.dateW : Font.Normal
            }
            Chip_ {
                visible: login.showBattery
                anchors.horizontalCenter: parent.horizontalCenter
                icon: "battery"
                text: "82%"
            }
            Rectangle {
                objectName: "loginPreviewMessage"
                visible: login.showMessage
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(loginMsg.implicitWidth, root.u(620)) + root.u(34)
                height: loginMsg.height + root.u(20)
                radius: root.u(16)
                color: Qt.rgba(1, 1, 1, 0.09)
                border.width: Math.max(1, root.u(1))
                border.color: Qt.rgba(1, 1, 1, 0.16)
                Text {
                    id: loginMsg
                    anchors.centerIn: parent
                    width: Math.min(implicitWidth, root.u(620))
                    text: login.look.message || ""
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    color: "white"
                    font.pixelSize: root.pt(11.5)
                    font.weight: Font.Medium
                }
            }
        }

        // The user and the password field, on the glass card.
        Item {
            objectName: "loginPreviewPrompt"
            width: root.u(360)
            height: loginCol.height
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.max(root.height * 0.47, root.height - height - root.u(150))
            Rectangle {
                objectName: "loginPreviewCard"
                visible: login.look.card === true
                x: -root.u(28); y: -root.u(28)
                width: parent.width + root.u(56); height: parent.height + root.u(56)
                radius: Math.min(root.u(32), height / 2)
                color: Qt.rgba(1, 1, 1, 0.06 + 0.06 * (login.look.frost ?? 0.35))
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
                id: loginCol
                width: parent.width
                spacing: root.u(16)
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: root.u(112); height: width; radius: width / 2
                    color: Qt.rgba(1, 1, 1, 0.16)
                    Icon { anchors.centerIn: parent; name: "user"; size: root.u(56); color: "white"; layered: false }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: Backend.userName || qsTr("You")
                    color: "white"
                    font.pixelSize: root.pt(14)
                    font.weight: Font.Bold
                }
                Rectangle {
                    width: parent.width; height: root.u(48); radius: root.u(12)
                    color: Qt.rgba(1, 1, 1, 0.08 + 0.12 * (login.look.frost ?? 0.35))
                    border.width: Math.max(1, root.u(2))
                    border.color: login.look.accent || Theme.accent
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: root.u(16)
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Password")
                        color: Qt.rgba(1, 1, 1, 0.55)
                        font.pixelSize: root.pt(11.5)
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
