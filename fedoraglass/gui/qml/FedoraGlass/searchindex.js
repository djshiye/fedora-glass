.pragma library
// Every setting search can find: what people call it, other words they might type,
// the page it lives on and the objectName of the control that search lights up.
// `en` and `ew` (English label and words) stay English, so English words always find the entry;
// `title` and `tw` are the same text in the person's language: shown as the result, and searched too.
// A test checks that every name here exists on its page. `needs` names what the control
// needs to show at all (see Sidebar.available): without it, search doesn't offer it.

var entries = [
    // Home
    { en: "Look presets", title: qsTr("Look presets"), ew: "liquid clear balanced frosted solid preset style start", tw: qsTr("liquid clear balanced frosted solid preset style start"), page: "home", name: "presetRow" },
    // Colour
    { en: "Light or dark style", title: qsTr("Light or dark style"), ew: "dark light auto scheme mode night", tw: qsTr("dark light auto scheme mode night"), page: "colour", name: "schemeChoice" },
    { en: "Accent colour", title: qsTr("Accent colour"), ew: "accent color highlight system custom", tw: qsTr("accent color highlight system custom"), page: "colour", name: "accentRow" },
    { en: "Tint colour", title: qsTr("Tint colour"), ew: "tint color hue glass colour", tw: qsTr("tint color hue glass colour"), page: "colour", name: "tintButton" },
    { en: "Tint strength", title: qsTr("Tint strength"), ew: "tint amount color strength", tw: qsTr("tint amount color strength"), page: "colour", name: "tintStrength" },
    { en: "Corner roundness", title: qsTr("Corner roundness"), ew: "corners radius round rounded sharp", tw: qsTr("corners radius round rounded sharp"), page: "colour", name: "cornerRoundness" },
    // Glass
    { en: "How much glass", title: qsTr("How much glass"), ew: "frost frosted liquid clear glass amount milky", tw: qsTr("frost frosted liquid clear glass amount milky"), page: "glass", name: "glassFrost" },
    { en: "Bend", title: qsTr("Bend"), ew: "refraction lens bend edge thickness strength", tw: qsTr("refraction lens bend edge thickness strength"), page: "glass", name: "bend" },
    { en: "Rainbow edge", title: qsTr("Rainbow edge"), ew: "dispersion rainbow chromatic fringe colour edge", tw: qsTr("dispersion rainbow chromatic fringe colour edge"), page: "glass", name: "rainbowEdge" },
    { en: "Colour through glass", title: qsTr("Colour through glass"), ew: "vibrancy saturation vivid colour through", tw: qsTr("vibrancy saturation vivid colour through"), page: "glass", name: "colourThroughGlass" },
    { en: "Colour bleed", title: qsTr("Colour bleed"), ew: "bleed glow icons light spread", tw: qsTr("bleed glow icons light spread"), page: "glass", name: "colourBleed" },
    { en: "Light follows pointer", title: qsTr("Light follows pointer"), ew: "pointer light mouse highlight follow", tw: qsTr("pointer light mouse highlight follow"), page: "glass", name: "lightFollowsPointer" },
    { en: "Glass on the panel", title: qsTr("Glass on the panel"), ew: "panel taskbar top bar dock glass where", tw: qsTr("panel taskbar top bar dock glass where"), page: "glass", name: "glassPanel" },
    { en: "Glass on menus", title: qsTr("Glass on menus"), ew: "menus popups quick settings calendar glass where", tw: qsTr("menus popups quick settings calendar glass where"), page: "glass", name: "glassMenus" },
    { en: "Glass behind app windows", title: qsTr("Glass behind app windows"), ew: "app windows translucent blur behind where", tw: qsTr("app windows translucent blur behind where"), page: "glass", name: "glassAppWindows" },
    { en: "Glass in the overview", title: qsTr("Glass in the overview"), ew: "overview activities blur where", tw: qsTr("overview activities blur where"), page: "glass", name: "glassOverview" },
    { en: "See windows through the glass", title: qsTr("See windows through the glass"), ew: "see through windows behind blur gpu", tw: qsTr("see through windows behind blur gpu"), page: "glass", name: "glassSeeWindows" },
    { en: "Speed and glass quality", title: qsTr("Speed and glass quality"), ew: "speed quality performance fps gpu lighter lightest auto check", tw: qsTr("speed quality performance fps gpu lighter lightest auto check"), page: "glass", name: "speedCard" },
    // Panel and windows
    { en: "Panel floating or docked", title: qsTr("Panel floating or docked"), ew: "dash to panel floating docked pill bar style", tw: qsTr("dash to panel floating docked pill bar style"), page: "windows", name: "panelStyle", needs: "dtp" },
    { en: "Panel margin", title: qsTr("Panel margin"), ew: "panel gap margin edge floating", tw: qsTr("panel gap margin edge floating"), page: "windows", name: "panelMargin", needs: "dtp" },
    { en: "Header bar height", title: qsTr("Header bar height"), ew: "header bar title bar height size compact", tw: qsTr("header bar title bar height size compact"), page: "windows", name: "headerHeight" },
    { en: "Header bar opacity", title: qsTr("Header bar opacity"), ew: "header bar transparency opacity see through", tw: qsTr("header bar transparency opacity see through"), page: "windows", name: "headerOpacity" },
    { en: "Terminal follows light and dark", title: qsTr("Terminal follows light and dark"), ew: "terminal ptyxis light dark follow", tw: qsTr("terminal ptyxis light dark follow"), page: "windows", name: "terminalFollowsStyle" },
    { en: "Terminal colours", title: qsTr("Terminal colours"), ew: "terminal colours palette colors", tw: qsTr("terminal colours palette colors"), page: "windows", name: "terminalColors" },
    { en: "Qt apps title bar", title: qsTr("Qt apps title bar"), ew: "qt kde title bar x11 keepassxc", tw: qsTr("qt kde title bar x11 keepassxc"), page: "windows", name: "qtGnomeTitlebars" },
    // Motion
    { en: "Motion style", title: qsTr("Motion style"), ew: "animation motion calm lively playful off gnome", tw: qsTr("animation motion calm lively playful off gnome"), page: "motion", name: "motionStyle" },
    { en: "Animation speed", title: qsTr("Animation speed"), ew: "speed animation slower faster", tw: qsTr("speed animation slower faster"), page: "motion", name: "motionSpeed" },
    { en: "Liquid motion", title: qsTr("Liquid motion"), ew: "liquid spring press settle", tw: qsTr("liquid spring press settle"), page: "motion", name: "liquidMotion" },
    { en: "How liquid", title: qsTr("How liquid"), ew: "liquid stretch press wobble soft taskbar", tw: qsTr("liquid stretch press wobble soft taskbar"), page: "motion", name: "liquidStrength" },
    { en: "Menus grow from their button", title: qsTr("Menus grow from their button"), ew: "menu grow open animation", tw: qsTr("menu grow open animation"), page: "motion", name: "menuGrow" },
    { en: "Gliding highlight", title: qsTr("Gliding highlight"), ew: "taskbar hover highlight glide", tw: qsTr("taskbar hover highlight glide"), page: "motion", name: "motionGlide", needs: "dtp" },
    { en: "Dash to Panel's own hover animation", title: qsTr("Dash to Panel's own hover animation"), ew: "dash to panel hover animation taskbar icons bounce", tw: qsTr("dash to panel hover animation taskbar icons bounce"), page: "motion", name: "motionDtpNote", needs: "dtpHover" },
    { en: "Each animation on its own", title: qsTr("Each animation on its own"), ew: "open minimize close app starting launch bounce panel hover genie jelly", tw: qsTr("open minimize close app starting launch bounce panel hover genie jelly"), page: "motion", name: "eachAnimation" },
    // Pointer and desktop
    { en: "Mouse pointer style", title: qsTr("Mouse pointer style"), ew: "cursor pointer mouse arrow style", tw: qsTr("cursor pointer mouse arrow style"), page: "pointer", name: "cursorCard" },
    { en: "Pointer size", title: qsTr("Pointer size"), ew: "cursor pointer size large small", tw: qsTr("cursor pointer size large small"), page: "pointer", name: "cursorSize" },
    { en: "Start on the desktop", title: qsTr("Start on the desktop"), ew: "start desktop login overview boot", tw: qsTr("start desktop login overview boot"), page: "pointer", name: "startOnDesktop" },
    { en: "Turn off the overview", title: qsTr("Turn off the overview"), ew: "overview activities super key hot corner off", tw: qsTr("overview activities super key hot corner off"), page: "pointer", name: "overviewOff" },
    // Lock and login
    { en: "Glass lock screen", title: qsTr("Glass lock screen"), ew: "lock screen glass", tw: qsTr("lock screen glass"), page: "lock", name: "lockGlass" },
    { en: "Lock screen frost", title: qsTr("Lock screen frost"), ew: "lock blur frost", tw: qsTr("lock blur frost"), page: "lock", name: "lockBlur" },
    { en: "Lock screen clock style", title: qsTr("Lock screen clock style"), ew: "clock bold thin font lock", tw: qsTr("clock bold thin font lock"), page: "lock", name: "lockClock" },
    { en: "Battery on the lock screen", title: qsTr("Battery on the lock screen"), ew: "battery widget lock", tw: qsTr("battery widget lock"), page: "lock", name: "lockWidgetBattery" },
    { en: "Weather on the lock screen", title: qsTr("Weather on the lock screen"), ew: "weather widget lock place city", tw: qsTr("weather widget lock place city"), page: "lock", name: "lockWidgetWeather" },
    { en: "Greeting on the lock screen", title: qsTr("Greeting on the lock screen"), ew: "greeting hello name lock", tw: qsTr("greeting hello name lock"), page: "lock", name: "lockGreeting" },
    { en: "Message on the lock screen", title: qsTr("Message on the lock screen"), ew: "message text note lost laptop lock", tw: qsTr("message text note lost laptop lock"), page: "lock", name: "lockMessageChip" },
    { en: "Name the place for weather", title: qsTr("Name the place for weather"), ew: "weather place town city location privacy lock", tw: qsTr("weather place town city location privacy lock"), page: "lock", name: "lockWeatherPlace" },
    { en: "Lock screen widget look", title: qsTr("Lock screen widget look"), ew: "widgets look glass chips text only plain lock", tw: qsTr("widgets look glass chips text only plain lock"), page: "lock", name: "lockWidgetStyle" },
    { en: "Hide notifications on the lock screen", title: qsTr("Hide notifications on the lock screen"), ew: "privacy notifications music hide lock", tw: qsTr("privacy notifications music hide lock"), page: "lock", name: "lockHideNotifications" },
    { en: "Lock screen darken", title: qsTr("Lock screen darken"), ew: "darken dim lock", tw: qsTr("darken dim lock"), page: "lock", name: "lockDim" },
    { en: "Lock screen tint", title: qsTr("Lock screen tint"), ew: "tint colour lock", tw: qsTr("tint colour lock"), page: "lock", name: "lockTint" },
    { en: "Glass card behind the password", title: qsTr("Glass card behind the password"), ew: "password card pane lock", tw: qsTr("password card pane lock"), page: "lock", name: "lockCard" },
    { en: "Clock position", title: qsTr("Clock position"), ew: "clock position top middle lock", tw: qsTr("clock position top middle lock"), page: "lock", name: "lockClockPosition" },
    { en: "Unlock animation", title: qsTr("Unlock animation"), ew: "unlock slide bounce animation", tw: qsTr("unlock slide bounce animation"), page: "lock", name: "lockSlide" },
    { en: "Unlock slide time", title: qsTr("Unlock slide time"), ew: "unlock slide time speed duration slower faster lock", tw: qsTr("unlock slide time speed duration slower faster lock"), page: "lock", name: "lockSlideMs" },
    { en: "Unlock bounce", title: qsTr("Unlock bounce"), ew: "unlock bounce spring dip lock", tw: qsTr("unlock bounce spring dip lock"), page: "lock", name: "lockBounce" },
    { en: "Glass login screen", title: qsTr("Glass login screen"), ew: "login gdm greeter screen password", tw: qsTr("login gdm greeter screen password"), page: "lock", name: "loginCard", needs: "login" },
    // Apps
    { en: "Apps that get themed", title: qsTr("Apps that get themed"), ew: "apps gtk libadwaita libreoffice firefox themed targets", tw: qsTr("apps gtk libadwaita libreoffice firefox themed targets"), page: "apps", name: "appsList" },
    // Advanced
    { en: "Part by part", title: qsTr("Part by part"), ew: "part panel start menu quick settings calendar windows terminal own look override", tw: qsTr("part panel start menu quick settings calendar windows terminal own look override"), page: "advanced", name: "partRow" },
    { en: "Transparency", title: qsTr("Transparency"), ew: "opacity transparency solid fine tune", tw: qsTr("opacity transparency solid fine tune"), page: "advanced", name: "fineOpacity" },
    { en: "Blur", title: qsTr("Blur"), ew: "blur radius px fine tune", tw: qsTr("blur radius px fine tune"), page: "advanced", name: "fineBlur" },
    { en: "Terminal opacity", title: qsTr("Terminal opacity"), ew: "terminal opacity transparency see through", tw: qsTr("terminal opacity transparency see through"), page: "advanced", name: "fineTerminalOpacity" },
    { en: "Reduce transparency", title: qsTr("Reduce transparency"), ew: "reduce transparency readability opaque accessibility", tw: qsTr("reduce transparency readability opaque accessibility"), page: "advanced", name: "reduceTransparency" },
    { en: "Reset everything to defaults", title: qsTr("Reset everything to defaults"), ew: "reset defaults start over", tw: qsTr("reset defaults start over"), page: "advanced", name: "resetAll" },
    // About and restore
    { en: "Restore original look", title: qsTr("Restore original look"), ew: "restore original undo revert remove back", tw: qsTr("restore original undo revert remove back"), page: "about", name: "restoreOriginal" },
    { en: "Remove Fedora Glass", title: qsTr("Remove Fedora Glass"), ew: "remove uninstall delete", tw: qsTr("remove uninstall delete"), page: "about", name: "removeApp", needs: "removable" },
    { en: "Put my original look back on removal", title: qsTr("Put my original look back on removal"), ew: "remove uninstall original look back restore keep", tw: qsTr("remove uninstall original look back restore keep"), page: "about", name: "undoOnRemove" },
    { en: "Keyboard shortcuts", title: qsTr("Keyboard shortcuts"), ew: "keyboard shortcuts keys help", tw: qsTr("keyboard shortcuts keys help"), page: "about", name: "shortcutsButton" },
    { en: "Version and what's new", title: qsTr("Version and what's new"), ew: "version about what's new changelog update", tw: qsTr("version about what's new changelog update"), page: "about", name: "aboutVersion" },
    // Firefox theme
    { en: "Firefox colours", title: qsTr("Firefox colours"), ew: "firefox browser mozilla theme toolbar tabs userchrome", tw: qsTr("firefox browser mozilla theme toolbar tabs userchrome"), page: "apps", name: "appsList" },
    // Shell features: lighter glass on battery, apps without glass, the Quick Settings switch
    { en: "Lighter glass on battery", title: qsTr("Lighter glass on battery"), ew: "battery power saver laptop energy lighter speed quality", tw: qsTr("battery power saver laptop energy lighter speed quality"), page: "glass", name: "lighterOnBattery" },
    { en: "Apps with their own glass", title: qsTr("Apps with their own glass"), ew: "apps without windows no glass skip exclude games video steam list more solid clearer strength per app", tw: qsTr("apps without windows no glass skip exclude games video steam list more solid clearer strength per app"), page: "windows", name: "noGlassCard" },
    { en: "Glass switch in Quick Settings", title: qsTr("Glass switch in Quick Settings"), ew: "quick settings tile pause turn off glass toggle switch menu", tw: qsTr("quick settings tile pause turn off glass toggle switch menu"), page: "glass", name: "quickToggle" },
    // Feature stream "looks"
    { en: "Save this look", title: qsTr("Save this look"), ew: "save my look name keep favourite", tw: qsTr("save my look name keep favourite"), page: "home", name: "saveLook" },
    { en: "Add a look from a file", title: qsTr("Add a look from a file"), ew: "import open share look file json", tw: qsTr("import open share look file json"), page: "home", name: "importLook" },
    { en: "Your saved looks", title: qsTr("Your saved looks"), ew: "my looks saved rename delete export share file", tw: qsTr("my looks saved rename delete export share file"), page: "home", name: "savedLooks", needs: "looks" },
    { en: "Tint matches my wallpaper", title: qsTr("Tint matches my wallpaper"), ew: "wallpaper background match tint colour automatic picture", tw: qsTr("wallpaper background match tint colour automatic picture"), page: "colour", name: "wallpaperTint" },
    { en: "Accent matches my wallpaper", title: qsTr("Accent matches my wallpaper"), ew: "wallpaper background match accent colour automatic picture", tw: qsTr("wallpaper background match accent colour automatic picture"), page: "colour", name: "wallpaperAccent" },
    { en: "Go back one Apply", title: qsTr("Go back one Apply"), ew: "previous last apply undo back forward before earlier look", tw: qsTr("previous last apply undo back forward before earlier look"), page: "about", name: "goToPrevious", needs: "previous" }
]

// Lower case, accents dropped (so "cafe" finds "café"), anything but letters and digits a space.
function norm(s) {
    var t = String(s).toLowerCase()
    if (t.normalize)
        t = t.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    return t.replace(/[^a-z0-9\u00c0-\uffff ]+/g, " ")
}

// Every match, best first: a label that starts with the query, then a word that does, then
// any match. `available` maps each `needs` to whether that control shows here; an entry
// whose `needs` isn't true there is left out (a missing map leaves everything in).
function matches(query, pageLabels, available) {
    var q = norm(query).trim()
    if (!q.length)
        return []
    var parts = q.split(/\s+/)
    var scored = []
    for (var i = 0; i < entries.length; ++i) {
        var e = entries[i]
        if (e.needs && available && available[e.needs] !== true)
            continue
        var label = norm(e.en)
        var hay = label + " " + norm(e.ew) + " " + norm(e.title) + " " + norm(e.tw) + " " + norm(pageLabels[e.page] || "")
        var ok = true
        for (var j = 0; j < parts.length; ++j)
            if (hay.indexOf(parts[j]) < 0) { ok = false; break }
        if (!ok)
            continue
        var title = norm(e.title)
        var score = label.indexOf(q) === 0 || title.indexOf(q) === 0 ? 0 : (" " + label).indexOf(" " + parts[0]) >= 0 || (" " + title).indexOf(" " + parts[0]) >= 0 ? 1
                  : (" " + hay).indexOf(" " + parts[0]) >= 0 ? 2 : 3
        scored.push({ score: score, i: i, e: e })
    }
    scored.sort(function (a, b) { return a.score - b.score || a.i - b.i })
    return scored.map(function (s) { return s.e })
}

function search(query, pageLabels, limit, available) {
    return matches(query, pageLabels, available).slice(0, limit || 7)
}
