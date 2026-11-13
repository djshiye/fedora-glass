import QtQuick
import FedoraGlass.Core

// Weather frost: the glass frosts over as it gets cold where you are, and is just as you
// set it when it feels comfortable outside. The temperature is GNOME's own weather for
// the place set in GNOME Weather; the Shell extension (frost.js) reads it, never the app.
// Like day and night looks, once applied the weather changes the desktop by itself, so
// the switch's caption says so. The temperatures and the Try row only change the preview
// until Apply.
Card {
    id: card
    objectName: "weatherFrost"
    height: implicitHeight

    readonly property bool on: Backend.weatherFrost
    readonly property var now: Backend.weatherNow
    readonly property var ranges: Backend.weatherRanges
    readonly property string why: Backend.weatherState     // ready, no-app or no-place
    function t(c) { return Backend.showTemp(c) }
    // What the desktop's glass does now, in a sentence.
    readonly property string status: {
        if (!on)
            return ""
        if (now.status === "ok")
            return reading()
        if (why === "no-app")
            return qsTr("Needs the GNOME Weather app. Install it from Software and pick your place, and the glass follows its weather.")
        if (why === "no-place" || now.status === "no-place")
            return qsTr("Pick your place in GNOME Weather, and the glass follows its weather.")
        if (now.status === "no-weather")
            return qsTr("GNOME's weather isn't available on this desktop yet.")
        if (now.status !== "ok")
            return now.status === "waiting" ? qsTr("Waiting for GNOME's weather…")
                                            : qsTr("Apply, and the glass starts following the weather.")
        return reading()
    }
    function reading() {
        const temp = Backend.weatherFeelsLike ? now.feels : now.temp
        const said = Backend.weatherFeelsLike ? qsTr("It feels like %1 outside").arg(t(temp))
                                              : qsTr("It is %1 outside").arg(t(temp))
        const level = now.level
        return level === "freezing" ? qsTr("%1: freezing, so the glass ices over.").arg(said)
             : level === "cold" ? qsTr("%1: cold, so the glass is frosted.").arg(said)
             : level === "cool" ? qsTr("%1: cool, so the glass mists over a little.").arg(said)
             : qsTr("%1: just right, so the glass looks as you set it.").arg(said)
    }

    Column {
        width: parent.width
        spacing: 6

        SectionTitle {
            text: qsTr("Weather frost")
            caption: qsTr("The glass frosts over as it gets cold where you are. When it feels just right outside, it looks exactly as you set it.")
            resetKeys: ["weather_frost", "weather_feels_like", "weather_cool", "weather_cold", "weather_freezing", "weather_amount"]
        }
        SwitchRow {
            objectName: "weatherFrostSwitch"
            label: qsTr("Frost with the weather")
            caption: qsTr("Uses the place in GNOME Weather. Once applied, the weather changes your glass by itself, like day and night looks.")
            tip: qsTr("Only GNOME's own weather is used, the one in its calendar menu: nothing new is told about where you are. Off, the glass never changes with the weather.")
            checked: card.on
            onToggled: (v) => Backend.weatherFrost = v
        }

        // What it does now on the desktop, and the way to GNOME Weather when it needs a place.
        Item {
            objectName: "weatherStatus"
            visible: card.status !== ""
            width: parent.width
            height: visible ? Math.max(statusRow.implicitHeight, openWeather.visible ? openWeather.height : 0) + 4 : 0
            Row {
                id: statusRow
                width: parent.width - (openWeather.visible ? openWeather.width + 12 : 0)
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Icon {
                    name: card.now.level === "freezing" || card.now.level === "cold" ? "snowflake" : "thermometer"
                    size: 16
                    color: Theme.accentText
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    objectName: "weatherStatusText"
                    width: parent.width - 24
                    text: card.status
                    wrapMode: Text.WordWrap
                    color: Theme.textDim
                    font.pixelSize: Theme.fsSmall + 1
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            LgButton {
                id: openWeather
                objectName: "openWeatherApp"
                visible: card.why === "no-place" || card.now.status === "no-place"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                implicitHeight: 32
                text: qsTr("Open GNOME Weather")
                onClicked: Backend.openWeatherApp()
            }
        }

        // The steps along the temperature, coldest left: where each begins, and where
        // it is now when weather frost has a reading.
        TempScale {
            objectName: "weatherScale"
            width: parent.width
        }

        Item { width: 1; height: 2 }
        Row {
            width: parent.width
            spacing: 12
            Text {
                id: tryLabel
                text: qsTr("Try in the preview")
                color: Theme.textDim
                font.pixelSize: Theme.fsSmall + 1
                font.weight: Font.Medium
                anchors.verticalCenter: parent.verticalCenter
            }
            Segmented {
                objectName: "weatherTry"
                width: parent.width - tryLabel.width - 12
                compact: true
                value: Backend.weatherTry
                model: [
                    { value: "", label: qsTr("Now"), tip: qsTr("The glass as the weather has it now") },
                    { value: "cool", label: qsTr("Cool"), tip: qsTr("A light mist, below %1").arg(card.t(Backend.weatherCool)) },
                    { value: "cold", label: qsTr("Cold"), tip: qsTr("Frosted glass, below %1").arg(card.t(Backend.weatherCold)) },
                    { value: "freezing", label: qsTr("Freezing"), tip: qsTr("Ice creeps in from the edges, below %1").arg(card.t(Backend.weatherFreezing)) }
                ]
                Accessible.name: qsTr("Try a step in the preview")
                onActivated: (v) => Backend.weatherTry = v
            }
        }
        Fold {
            objectName: "weatherSteps"
            card: false
            divider: true
            title: qsTr("Temperatures and frost")
            summary: qsTr("Cool below %1, cold below %2, icy below %3")
                     .arg(card.t(Backend.weatherCool)).arg(card.t(Backend.weatherCold)).arg(card.t(Backend.weatherFreezing))
            Column {
                width: parent.width
                spacing: 2
                LabeledSlider {
                    objectName: "weatherCool"
                    inline: true
                    label: qsTr("Cool below")
                    from: card.ranges.cool[0]; to: card.ranges.cool[1]; stepSize: 1
                    value: Backend.weatherCool
                    defaultValue: Backend.defaults.weather_cool
                    format: (v) => card.t(v)
                    onMoved: (v) => { Backend.weatherCool = v; Backend.weatherTry = "cool" }
                    tip: qsTr("Below this the glass starts to mist over. Outdoors, 18 to 23 °C is shirt-sleeve weather, so 18 °C is where most people start to feel cool.")
                }
                LabeledSlider {
                    objectName: "weatherCold"
                    inline: true
                    label: qsTr("Cold below")
                    from: card.ranges.cold[0]; to: card.ranges.cold[1]; stepSize: 1
                    value: Backend.weatherCold
                    defaultValue: Backend.defaults.weather_cold
                    format: (v) => card.t(v)
                    onMoved: (v) => { Backend.weatherCold = v; Backend.weatherTry = "cold" }
                    tip: qsTr("Below this the glass is frosted, whiter at its edges. Below 10 °C outdoors most people want a heavy coat.")
                }
                LabeledSlider {
                    objectName: "weatherFreezing"
                    inline: true
                    label: qsTr("Icy below")
                    from: card.ranges.freezing[0]; to: card.ranges.freezing[1]; stepSize: 1
                    value: Backend.weatherFreezing
                    defaultValue: Backend.defaults.weather_freezing
                    format: (v) => card.t(v)
                    onMoved: (v) => { Backend.weatherFreezing = v; Backend.weatherTry = "freezing" }
                    tip: qsTr("Below this, the glass ices over from its edges, thickest in the corners, like a car window on a winter morning. The middle, where text is, stays clear.")
                }
                LabeledSlider {
                    objectName: "weatherAmount"
                    inline: true
                    label: qsTr("How much frost")
                    from: 0.2; to: 1
                    value: Backend.weatherAmount
                    defaultValue: Backend.defaults.weather_amount
                    onMoved: (v) => { Backend.weatherAmount = v; if (Backend.weatherTry === "") Backend.weatherTry = "freezing" }
                    tip: qsTr("How far the frost goes at its coldest. Left is a hint of frost; right is fully frosted glass.")
                }
                Item {
                    width: parent.width
                    height: 44
                    Text {
                        id: byLabel
                        width: 170 - 12
                        text: qsTr("Go by")
                        color: Theme.text
                        font.pixelSize: Theme.fsBody
                        font.weight: Font.Medium
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Segmented {
                        objectName: "weatherFeelsLike"
                        x: 170
                        width: parent.width - 170
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        value: Backend.weatherFeelsLike
                        model: [
                            { value: true, label: qsTr("Feels like"), tip: qsTr("How cold it feels, with the wind and humidity, as GNOME Weather shows it") },
                            { value: false, label: qsTr("Air temperature"), tip: qsTr("The temperature of the air alone") }
                        ]
                        Accessible.name: qsTr("Go by")
                        onActivated: (v) => Backend.weatherFeelsLike = v
                    }
                }
            }
        }
    }

    // ---- the scale: four steps along the temperature ----------------------------------
    component TempScale: Item {
        id: ts
        readonly property real lo: Math.min(-15, Backend.weatherFreezing - 8)
        readonly property real hi: Math.max(30, Backend.weatherCool + 10)
        function xOf(c) { return Math.max(0, Math.min(1, (c - lo) / (hi - lo))) * bar.width }
        readonly property real nowTemp: card.on && card.now.status === "ok"
                                        ? (Backend.weatherFeelsLike ? card.now.feels : card.now.temp) : NaN
        implicitHeight: bar.height + 30
        Accessible.role: Accessible.StaticText
        Accessible.name: qsTr("Icy below %1, frosted below %2, misty below %3, just right above")
                         .arg(card.t(Backend.weatherFreezing)).arg(card.t(Backend.weatherCold)).arg(card.t(Backend.weatherCool))

        Rectangle {
            id: bar
            y: 4
            width: parent.width
            height: 10
            radius: height / 2
            clip: true
            color: "transparent"
            border.width: 1
            border.color: Theme.border
            // Icy white at the cold end, through pale blue, to the accent's calm at "just right".
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.dark ? "#e8f3ff" : "#cfe6ff" }
                GradientStop { position: ts.xOf(Backend.weatherFreezing) / Math.max(1, bar.width); color: Theme.dark ? "#b6d8fb" : "#a9d0f7" }
                GradientStop { position: ts.xOf(Backend.weatherCold) / Math.max(1, bar.width); color: Theme.dark ? "#7fa9d6" : "#86b5e6" }
                GradientStop { position: ts.xOf(Backend.weatherCool) / Math.max(1, bar.width); color: Theme.alpha(Theme.accent, 0.35) }
                GradientStop { position: 1; color: Theme.alpha(Theme.accent, 0.18) }
            }
        }
        Repeater {      // where each step begins
            model: [Backend.weatherFreezing, Backend.weatherCold, Backend.weatherCool]
            delegate: Rectangle {
                required property var modelData
                x: ts.xOf(modelData) - 1
                y: bar.y - 2
                width: 2; height: bar.height + 4
                radius: 1
                color: Theme.dark ? Qt.rgba(1, 1, 1, 0.75) : Qt.rgba(0.1, 0.12, 0.2, 0.45)
            }
        }
        Rectangle {     // it is here now
            objectName: "weatherNowMark"
            visible: !isNaN(ts.nowTemp)
            x: ts.xOf(ts.nowTemp) - width / 2
            y: bar.y + bar.height / 2 - height / 2
            width: 16; height: 16
            radius: 8
            color: Theme.accent
            border.width: 2
            border.color: "white"
        }
        Row {
            y: bar.y + bar.height + 8
            width: parent.width
            Repeater {
                model: [
                    { label: qsTr("Icy"), a: ts.lo, b: Backend.weatherFreezing },
                    { label: qsTr("Frosted"), a: Backend.weatherFreezing, b: Backend.weatherCold },
                    { label: qsTr("Misty"), a: Backend.weatherCold, b: Backend.weatherCool },
                    { label: qsTr("Just right"), a: Backend.weatherCool, b: ts.hi }
                ]
                delegate: Text {
                    required property var modelData
                    width: ts.xOf(modelData.b) - ts.xOf(modelData.a)
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    text: modelData.label
                    color: Theme.textFaint
                    font.pixelSize: Theme.fsSmall
                }
            }
        }
    }
}
