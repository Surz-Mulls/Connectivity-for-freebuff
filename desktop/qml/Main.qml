// Continuity desktop client. Pure QML: it is a client of the daemon's local HTTP bridge
// (token-guarded, loopback only) and holds no connection state of its own.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    width: 1020
    height: 700
    minimumWidth: 820
    minimumHeight: 560
    visible: true
    title: "Continuity"
    color: Theme.base

    property var status: ({})
    property var pendingPairing: null
    property var pendingTransfer: null
    property string apiToken: ""
    property int apiPort: 0
    property string apiConfig: ""
    property string lastError: ""
    property string toast: ""

    function argValue(prefix) {
        var args = Qt.application.arguments
        for (var i = 0; i < args.length; i++) {
            if (args[i].indexOf(prefix) === 0)
                return args[i].substring(prefix.length)
        }
        return ""
    }

    function refresh() {
        if (apiPort === 0)
            return
        var xhr = new XMLHttpRequest()
        xhr.open("GET", "http://127.0.0.1:" + apiPort + "/api/status")
        xhr.setRequestHeader("Authorization", "Bearer " + apiToken)
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== 4)
                return
            if (xhr.status === 200) {
                try {
                    root.status = JSON.parse(xhr.responseText)
                    root.lastError = ""
                    root.checkPrompts()
                } catch (e) {
                    root.lastError = "bad response: " + e
                }
            } else if (xhr.status !== 0) {
                root.lastError = "daemon refused the request (" + xhr.status + ")"
            }
        }
        xhr.send()
    }

    function command(name, payload, done) {
        var body = { cmd: name }
        if (payload)
            for (var key in payload) body[key] = payload[key]
        var xhr = new XMLHttpRequest()
        xhr.open("POST", "http://127.0.0.1:" + apiPort + "/api/command")
        xhr.setRequestHeader("Authorization", "Bearer " + apiToken)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== 4)
                return
            var parsed = null
            try { parsed = JSON.parse(xhr.responseText) } catch (e) { parsed = null }
            if (parsed && parsed.ok === false) {
                root.toast = name + ": " + parsed.code + " — " + parsed.message
            } else if (parsed && done) {
                done(parsed.result)
            }
            root.refresh()
        }
        xhr.send(JSON.stringify(body))
    }

    function checkPrompts() {
        root.pendingPairing = (status.pairing && status.pairing.pending && status.pairing.pending.length > 0)
            ? status.pairing.pending[0] : null
        var transfers = status.transfers || []
        var offer = null
        for (var i = 0; i < transfers.length; i++)
            if (transfers[i].state === "pending") offer = transfers[i]
        root.pendingTransfer = offer
    }

    // The daemon writes {"port":…,"token":…} to a 0600 runtime file. Reading it here keeps the
    // bearer token out of argv, where any local process could read it from /proc/<pid>/cmdline.
    function loadApiConfig(path) {
        var xhr = new XMLHttpRequest()
        try {
            xhr.open("GET", "file://" + path, false)
            xhr.send()
            var data = JSON.parse(xhr.responseText)
            apiPort = parseInt(data.port)
            apiToken = String(data.token)
        } catch (e) {
            lastError = "cannot read the daemon token file: " + e
        }
    }

    Component.onCompleted: {
        apiConfig = argValue("--api-config=")
        if (apiConfig !== "")
            loadApiConfig(apiConfig)
        else
            apiPort = parseInt(argValue("--api-port="))
        if (!apiPort || apiToken === "")
            lastError = "No daemon token. Start the daemon, then launch with desktop/run-continuity.sh."
        refresh()
    }

    Timer { interval: 1500; running: true; repeat: true; onTriggered: root.refresh() }
    Timer {
        id: toastTimer
        interval: 4000
        onTriggered: root.toast = ""
    }
    onToastChanged: if (toast !== "") toastTimer.restart()

    header: Rectangle {
        color: Theme.mantle
        height: 64
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            spacing: 16
            Rectangle {
                width: 34; height: 34; radius: 17
                color: (root.status.daemon ? Theme.ok : Theme.overlay0)
                Text {
                    anchors.centerIn: parent
                    text: "C"
                    color: Theme.base
                    font.bold: true
                    font.pixelSize: 18
                }
            }
            Column {
                Layout.fillWidth: true
                Text {
                    text: root.status.daemon ? root.status.daemon.device.name : "Continuity"
                    color: Theme.text
                    font.pixelSize: Theme.fonttitle
                    font.family: Theme.fontUi
                }
                Text {
                    text: root.status.daemon
                        ? "protocol v1 · port " + root.status.daemon.port + " · "
                          + root.status.daemon.capabilities.length + " capabilities"
                        : "daemon not reachable"
                    color: root.status.daemon ? Theme.subtext : Theme.error
                    font.pixelSize: Theme.fontcaption
                }
            }
            Button {
                text: (root.status.privacy && root.status.privacy.privacy_mode)
                      ? "Privacy mode: on" : "Privacy mode: off"
                onClicked: root.command("privacy.set",
                    { privacy_mode: !(root.status.privacy && root.status.privacy.privacy_mode) })
            }
            Button {
                text: "Run diagnostics"
                onClicked: root.command("diagnostics.run", null, function (result) {
                    root.toast = "Report: " + result.paths.markdown
                })
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Rectangle {
            visible: root.lastError !== ""
            Layout.fillWidth: true
            height: visible ? 44 : 0
            radius: Theme.radiusSm
            color: Theme.surface0
            Text {
                anchors.centerIn: parent
                text: root.lastError
                color: Theme.error
                font.pixelSize: Theme.fontbody
            }
        }

        Rectangle {
            visible: root.pendingPairing !== null
            Layout.fillWidth: true
            height: visible ? 68 : 0
            radius: Theme.radiusMd
            color: Theme.surface0
            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                Text {
                    Layout.fillWidth: true
                    color: Theme.text
                    text: root.pendingPairing
                        ? "Pairing request from " + root.pendingPairing.fingerprint.substring(0, 12)
                          + "… — confirm the code shown on the phone, then approve."
                        : ""
                }
                Button {
                    text: "Approve"
                    onClicked: root.command("pair.approve",
                        { fingerprint: root.pendingPairing.fingerprint, accept: true })
                }
                Button {
                    text: "Deny"
                    onClicked: root.command("pair.approve",
                        { fingerprint: root.pendingPairing.fingerprint, accept: false })
                }
            }
        }

        Rectangle {
            visible: root.pendingTransfer !== null
            Layout.fillWidth: true
            height: visible ? 68 : 0
            radius: Theme.radiusMd
            color: Theme.surface0
            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                Text {
                    Layout.fillWidth: true
                    color: Theme.text
                    text: root.pendingTransfer
                        ? "Incoming file from " + root.pendingTransfer.peer + ": "
                          + root.pendingTransfer.name + " ("
                          + Math.round(root.pendingTransfer.size / 1024) + " KiB)"
                        : ""
                }
                Button {
                    text: "Accept"
                    onClicked: root.command("file.accept",
                        { transfer_id: root.pendingTransfer.id, accept: true })
                }
                Button {
                    text: "Decline"
                    onClicked: root.command("file.accept",
                        { transfer_id: root.pendingTransfer.id, accept: false })
                }
            }
        }

        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { text: "Devices" }
            TabButton { text: "Transfers" }
            TabButton { text: "DeX Workspace" }
            TabButton { text: "Privacy" }
            TabButton { text: "Diagnostics" }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabs.currentIndex

            // ---------------------------------------------------------------- Devices
            DevicesPage { status: root.status; onCommand: root.command }
            // ---------------------------------------------------------------- Transfers
            TransfersPage { status: root.status; onCommand: root.command }
            // ---------------------------------------------------------------- DeX
            DexPage { status: root.status; onCommand: root.command }
            // ---------------------------------------------------------------- Privacy
            PrivacyPage { status: root.status; onCommand: root.command }
            // ---------------------------------------------------------------- Diagnostics
            DiagnosticsPage { status: root.status; onCommand: root.command }
        }
    }

    Rectangle {
        visible: root.toast !== ""
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 24
        width: Math.min(parent.width - 80, toastText.implicitWidth + 40)
        height: 44
        radius: Theme.radiusMd
        color: Theme.surface1
        Text {
            id: toastText
            anchors.centerIn: parent
            text: root.toast
            color: Theme.text
            font.pixelSize: Theme.fontbody
        }
    }
}
