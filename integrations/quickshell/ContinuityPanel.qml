// Continuity status panel for Quickshell.
//
// It renders ONLY backend state: the panel runs `continuityctl status --json` (the same allowlisted
// IPC surface as the CLI/Qt UI) and never keeps its own connection copy. Install instructions are in
// README.md; this file is not included automatically by any script.
//
// NOTE: authored against the documented Quickshell primitives (PanelWindow, Process, Text, Column,
// Row, Rectangle, MouseArea). It has NOT been executed against a live Quickshell — the build host has
// no Hyprland session. Treat it as unverified until you run it (see docs/feature-matrix.md D02).
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root

    property var status: ({})
    property string errorText: ""
    property var firstDevice: ({})

    function refresh() {
        if (!statusProcess.running)
            statusProcess.running = true
    }

    function runCommand(name, payload) {
        var args = ["continuityctl", "status", "--json"]
        if (name === "privacy") {
            args = ["continuityctl", "privacy", "--" + (status.privacy && status.privacy.privacy_mode ? "off" : "on")]
        } else if (name === "ring" && firstDevice.fingerprint) {
            args = ["continuityctl", "ring", firstDevice.fingerprint]
        } else if (name === "clipboard" && firstDevice.fingerprint) {
            args = ["continuityctl", "push-clipboard", firstDevice.fingerprint]
        }
        commandProcess.command = args
        commandProcess.running = true
    }

    Process {
        id: statusProcess
        command: ["continuityctl", "status", "--json"]
        running: false
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    root.status = JSON.parse(text)
                    root.errorText = ""
                    var devices = root.status.devices || []
                    root.firstDevice = devices.length > 0 ? devices[0] : ({})
                } catch (e) {
                    root.errorText = "cannot parse daemon status"
                }
            }
        }
        onExited: (code, status) => {
            if (code !== 0)
                root.errorText = "daemon not running"
        }
    }

    Process {
        id: commandProcess
        running: false
        onExited: root.refresh()
    }

    Timer {
        interval: 2000
        running: true
        repeat: true
        onTriggered: root.refresh()
    }

    PanelWindow {
        id: popup
        width: 360
        height: 320
        anchors { top: true; right: true }
        color: "#1e1e2e"

        Column {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            Text {
                text: "Continuity"
                color: "#cdd6f4"
                font.pixelSize: 18
                font.bold: true
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.errorText !== "" ? "#f38ba8" : "#a6adc8"
                font.pixelSize: 12
                text: root.errorText !== ""
                      ? root.errorText + " — start it with: continuityd run"
                      : (root.firstDevice.name
                         ? root.firstDevice.name + " · " + root.firstDevice.state
                         : "No device connected")
            }

            Text {
                visible: !!root.firstDevice.battery
                color: "#a6adc8"
                font.pixelSize: 12
                text: root.firstDevice.battery
                      ? "Battery " + root.firstDevice.battery.level + "%"
                        + (root.firstDevice.battery.charging ? " (charging)" : "")
                      : ""
            }

            Text {
                visible: (root.status.transfers || []).length > 0
                color: "#a6adc8"
                font.pixelSize: 12
                text: {
                    var transfers = root.status.transfers || []
                    if (transfers.length === 0) return ""
                    var t = transfers[transfers.length - 1]
                    return t.direction + " " + t.name + " · " + Math.round(t.progress * 100) + "%"
                }
            }

            Row {
                spacing: 8
                Rectangle {
                    width: 104; height: 32; radius: 8; color: "#313244"
                    Text {
                        anchors.centerIn: parent
                        color: "#cdd6f4"
                        font.pixelSize: 12
                        text: (root.status.privacy && root.status.privacy.privacy_mode)
                              ? "Privacy: on" : "Privacy: off"
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.runCommand("privacy")
                    }
                }
                Rectangle {
                    width: 80; height: 32; radius: 8; color: "#313244"
                    Text {
                        anchors.centerIn: parent
                        color: "#cdd6f4"; font.pixelSize: 12; text: "Ring"
                    }
                    MouseArea { anchors.fill: parent; onClicked: root.runCommand("ring") }
                }
                Rectangle {
                    width: 96; height: 32; radius: 8; color: "#313244"
                    Text {
                        anchors.centerIn: parent
                        color: "#cdd6f4"; font.pixelSize: 12; text: "Clipboard"
                    }
                    MouseArea { anchors.fill: parent; onClicked: root.runCommand("clipboard") }
                }
            }
        }
    }
}
