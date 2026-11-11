.pragma library
// Every setting search can find: what people call it, other words they might type,
// the page it lives on and the objectName of the control that search lights up.
// A test checks that every name here exists on its page. `when` names what the control
// needs to show at all (see Sidebar.available): without it, search doesn't offer it.

var entries = [
    // Home
    { label: "Look presets", words: "liquid clear balanced frosted solid preset style start", page: "home", name: "presetRow" },
    // Colour
    { label: "Light or dark style", words: "dark light auto scheme mode night", page: "colour", name: "schemeChoice" },
    { label: "Accent colour", words: "accent color highlight system custom", page: "colour", name: "accentRow" },
    { label: "Tint colour", words: "tint color hue glass colour", page: "colour", name: "tintButton" },
    { label: "Tint strength", words: "tint amount color strength", page: "colour", name: "tintStrength" },
    { label: "Corner roundness", words: "corners radius round rounded sharp", page: "colour", name: "cornerRoundness" },
    // Glass
    { label: "How much glass", words: "frost frosted liquid clear glass amount milky", page: "glass", name: "glassFrost" },
    { label: "Bend", words: "refraction lens bend edge thickness strength", page: "glass", name: "bend" },
    { label: "Rainbow edge", words: "dispersion rainbow chromatic fringe colour edge", page: "glass", name: "rainbowEdge" },
    { label: "Colour through glass", words: "vibrancy saturation vivid colour through", page: "glass", name: "colourThroughGlass" },
    { label: "Colour bleed", words: "bleed glow icons light spread", page: "glass", name: "colourBleed" },
    { label: "Light follows pointer", words: "pointer light mouse highlight follow", page: "glass", name: "lightFollowsPointer" },
    { label: "Glass on the panel", words: "panel taskbar top bar dock glass where", page: "glass", name: "glassPanel" },
    { label: "Glass on menus", words: "menus popups quick settings calendar glass where", page: "glass", name: "glassMenus" },
    { label: "Glass behind app windows", words: "app windows translucent blur behind where", page: "glass", name: "glassAppWindows" },
    { label: "Glass in the overview", words: "overview activities blur where", page: "glass", name: "glassOverview" },
    { label: "See windows through the glass", words: "see through windows behind blur gpu", page: "glass", name: "glassSeeWindows" },
    { label: "Speed and glass quality", words: "speed quality performance fps gpu lighter lightest auto check", page: "glass", name: "speedCard" },
    // Panel and windows
    { label: "Panel floating or docked", words: "dash to panel floating docked pill bar style", page: "windows", name: "panelStyle", when: "dtp" },
    { label: "Panel margin", words: "panel gap margin edge floating", page: "windows", name: "panelMargin", when: "dtp" },
    { label: "Header bar height", words: "header bar title bar height size compact", page: "windows", name: "headerHeight" },
    { label: "Header bar opacity", words: "header bar transparency opacity see through", page: "windows", name: "headerOpacity" },
    { label: "Terminal follows light and dark", words: "terminal ptyxis light dark follow", page: "windows", name: "terminalFollowsStyle" },
    { label: "Terminal colours", words: "terminal colours palette colors", page: "windows", name: "terminalColors" },
    { label: "Qt apps title bar", words: "qt kde title bar x11 keepassxc", page: "windows", name: "qtGnomeTitlebars" },
    // Motion
    { label: "Motion style", words: "animation motion calm lively playful off gnome", page: "motion", name: "motionStyle" },
    { label: "Animation speed", words: "speed animation slower faster", page: "motion", name: "motionSpeed" },
    { label: "Liquid motion", words: "liquid spring press settle", page: "motion", name: "liquidMotion" },
    { label: "Menus grow from their button", words: "menu grow open animation", page: "motion", name: "menuGrow" },
    { label: "Gliding highlight", words: "taskbar hover highlight glide", page: "motion", name: "motionGlide", when: "dtp" },
    { label: "Dash to Panel's own hover animation", words: "dash to panel hover animation taskbar icons bounce", page: "motion", name: "motionDtpNote", when: "dtpHover" },
    { label: "Each animation on its own", words: "open minimize close app starting launch bounce panel hover genie jelly", page: "motion", name: "eachAnimation" },
    // Pointer and desktop
    { label: "Mouse pointer style", words: "cursor pointer mouse arrow style", page: "pointer", name: "cursorCard" },
    { label: "Pointer size", words: "cursor pointer size large small", page: "pointer", name: "cursorSize" },
    { label: "Start on the desktop", words: "start desktop login overview boot", page: "pointer", name: "startOnDesktop" },
    { label: "Turn off the overview", words: "overview activities super key hot corner off", page: "pointer", name: "overviewOff" },
    // Lock and login
    { label: "Glass lock screen", words: "lock screen glass", page: "lock", name: "lockGlass" },
    { label: "Lock screen frost", words: "lock blur frost", page: "lock", name: "lockBlur" },
    { label: "Lock screen clock style", words: "clock bold thin font lock", page: "lock", name: "lockClock" },
    { label: "Battery on the lock screen", words: "battery widget lock", page: "lock", name: "lockWidgetBattery" },
    { label: "Weather on the lock screen", words: "weather widget lock place city", page: "lock", name: "lockWidgetWeather" },
    { label: "Greeting on the lock screen", words: "greeting hello name lock", page: "lock", name: "lockGreeting" },
    { label: "Message on the lock screen", words: "message text note lost laptop lock", page: "lock", name: "lockMessageChip" },
    { label: "Name the place for weather", words: "weather place town city location privacy lock", page: "lock", name: "lockWeatherPlace" },
    { label: "Lock screen widget look", words: "widgets look glass chips text only plain lock", page: "lock", name: "lockWidgetStyle" },
    { label: "Hide notifications on the lock screen", words: "privacy notifications music hide lock", page: "lock", name: "lockHideNotifications" },
    { label: "Lock screen darken", words: "darken dim lock", page: "lock", name: "lockDim" },
    { label: "Lock screen tint", words: "tint colour lock", page: "lock", name: "lockTint" },
    { label: "Glass card behind the password", words: "password card pane lock", page: "lock", name: "lockCard" },
    { label: "Clock position", words: "clock position top middle lock", page: "lock", name: "lockClockPosition" },
    { label: "Unlock animation", words: "unlock slide bounce animation", page: "lock", name: "lockSlide" },
    { label: "Unlock slide time", words: "unlock slide time speed duration slower faster lock", page: "lock", name: "lockSlideMs" },
    { label: "Unlock bounce", words: "unlock bounce spring dip lock", page: "lock", name: "lockBounce" },
    { label: "Glass login screen", words: "login gdm greeter screen password", page: "lock", name: "loginCard", when: "login" },
    // Apps
    { label: "Apps that get themed", words: "apps gtk libadwaita libreoffice firefox themed targets", page: "apps", name: "appsList" },
    // Advanced
    { label: "Part by part", words: "part panel start menu quick settings calendar windows terminal own look override", page: "advanced", name: "partRow" },
    { label: "Transparency", words: "opacity transparency solid fine tune", page: "advanced", name: "fineOpacity" },
    { label: "Blur", words: "blur radius px fine tune", page: "advanced", name: "fineBlur" },
    { label: "Terminal opacity", words: "terminal opacity transparency see through", page: "advanced", name: "fineTerminalOpacity" },
    { label: "Reduce transparency", words: "reduce transparency readability opaque accessibility", page: "advanced", name: "reduceTransparency" },
    { label: "Reset everything to defaults", words: "reset defaults start over", page: "advanced", name: "resetAll" },
    // About and restore
    { label: "Restore original look", words: "restore original undo revert remove back", page: "about", name: "restoreOriginal" },
    { label: "Remove Fedora Glass", words: "remove uninstall delete", page: "about", name: "removeApp", when: "removable" },
    { label: "Put my original look back on removal", words: "remove uninstall original look back restore keep", page: "about", name: "undoOnRemove" },
    { label: "Keyboard shortcuts", words: "keyboard shortcuts keys help", page: "about", name: "shortcutsButton" },
    { label: "Version and what's new", words: "version about what's new changelog update", page: "about", name: "aboutVersion" },
    // Shell features: lighter glass on battery, apps without glass
    { label: "Lighter glass on battery", words: "battery power saver laptop energy lighter speed quality", page: "glass", name: "lighterOnBattery" },
    { label: "Apps without glass", words: "apps windows no glass skip exclude games video steam list", page: "windows", name: "noGlassCard" }
]

function norm(s) { return String(s).toLowerCase().replace(/[^a-z0-9 ]+/g, " ") }

// Every match, best first: a label that starts with the query, then a word that does, then
// any match. `available` maps each `when` to whether that control shows here; an entry
// whose `when` isn't true there is left out (a missing map leaves everything in).
function matches(query, pageLabels, available) {
    var q = norm(query).trim()
    if (!q.length)
        return []
    var parts = q.split(/\s+/)
    var scored = []
    for (var i = 0; i < entries.length; ++i) {
        var e = entries[i]
        if (e.when && available && available[e.when] !== true)
            continue
        var label = norm(e.label)
        var hay = label + " " + norm(e.words) + " " + norm(pageLabels[e.page] || "")
        var ok = true
        for (var j = 0; j < parts.length; ++j)
            if (hay.indexOf(parts[j]) < 0) { ok = false; break }
        if (!ok)
            continue
        var score = label.indexOf(q) === 0 ? 0 : (" " + label).indexOf(" " + parts[0]) >= 0 ? 1
                  : (" " + hay).indexOf(" " + parts[0]) >= 0 ? 2 : 3
        scored.push({ score: score, i: i, e: e })
    }
    scored.sort(function (a, b) { return a.score - b.score || a.i - b.i })
    return scored.map(function (s) { return s.e })
}

function search(query, pageLabels, limit, available) {
    return matches(query, pageLabels, available).slice(0, limit || 7)
}
