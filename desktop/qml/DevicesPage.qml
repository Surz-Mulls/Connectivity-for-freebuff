import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var status: ({})
    signal command(string name, var payload, var done)

    RowLayout {
        anchors.fill: parent
        spacing: 16

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: 620
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "Devices"
                    color: Theme.text
                    font.pixelSize: Theme.fontheadline
                    Layout.fillWidth: true
                }
                Button {
                    text: "Discover"
                    onClicked: page.command("pair.discover", { timeout: 3 })
                }
                Button {
                    text: "Show pairing QR"
                    onClicked: page.command("pair.begin", null, function (result) {
                        qrDialog.uri = result.uri
                        qrDialog.qrPath = result.qr_svg || ""
                        qrDialog.open()
                    })
                }
            }

            Text {
                visible: (page.status.devices || []).length === 0
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.subtext
                text: "No devices connected. Run the Android app, pair with the code below, and "
                      + "both sides must show the same 6 digits and 4 symbols."
            }

            Repeater {
                model: page.status.devices || []
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    height: 96
                    radius: Theme.radiusMd
                    color: Theme.surface0
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: modelData.name || modelData.id
                                color: Theme.text
                                font.pixelSize: Theme.fonttitle
                                Layout.fillWidth: true
                            }
                            Text {
                                text: modelData.state
                                color: modelData.state === "connected" ? Theme.stateConnected
                                     : modelData.state === "unpaired" ? Theme.statePermissionRequired
                                     : Theme.overlay0
                                font.pixelSize: Theme.fontcaption
                            }
                        }
                        Text {
                            text: modelData.platform + " · " + modelData.address
                                  + (modelData.battery && modelData.battery.level !== null
                                     ? " · battery " + modelData.battery.level + "%" : "")
                                  + (modelData.rtt_ms !== null ? " · " + modelData.rtt_ms + " ms" : "")
                            color: Theme.subtext
                            font.pixelSize: Theme.fontcaption
                        }
                        RowLayout {
                            spacing: 8
                            Button {
                                text: "Ping"
                                onClicked: page.command("find.ping", { fingerprint: modelData.fingerprint })
                            }
                            Button {
                                text: "Ring"
                                onClicked: page.command("find.ring", { fingerprint: modelData.fingerprint, duration_s: 10 })
                            }
                            Button {
                                text: "Push clipboard"
                                onClicked: page.command("clipboard.push", { fingerprint: modelData.fingerprint })
                            }
                            Button {
                                text: "Send file…"
                                onClicked: fileDialog.open()
                            }
                            Button {
                                text: "Revoke"
                                onClicked: page.command("trust.revoke", { fingerprint: modelData.fingerprint })
                            }
                        }
                    }
                    FileDialog {
                        id: fileDialog
                        title: "Send to " + modelData.name
                        onAccepted: page.command("file.send",
                            { fingerprint: modelData.fingerprint, path: fileDialog.selectedFile.toString() })
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: 320
            spacing: 8
            Text {
                text: "Paired (trust store)"
                color: Theme.text
                font.pixelSize: Theme.fonttitle
            }
            Repeater {
                model: page.status.trusted || []
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    height: 54
                    radius: Theme.radiusSm
                    color: Theme.mantle
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        Text {
                            text: modelData.name + (modelData.platform ? " (" + modelData.platform + ")" : "")
                            color: Theme.text
                            font.pixelSize: Theme.fontbody
                        }
                        Text {
                            text: modelData.fingerprint.substring(0, 24) + "…"
                            color: Theme.overlay0
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fontcaption
                        }
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }
    }

    Dialog {
        id: qrDialog
        property string uri: ""
        property string qrPath: ""
        title: "Pair a phone"
        modal: true
        anchors.centerIn: parent
        width: 420
        ColumnLayout {
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.text
                text: "Scan this with the Continuity Android app, then confirm the matching code "
                      + "on both devices."
            }
            Image {
                Layout.preferredWidth: 260
                Layout.preferredHeight: 260
                source: qrDialog.qrPath !== "" ? "file://" + qrDialog.qrPath : ""
                fillMode: Image.PreserveAspectFit
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WrapAnywhere
                color: Theme.subtext
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontcaption
                text: qrDialog.uri
            }
            Button {
                text: "Close"
                onClicked: qrDialog.close()
            }
        }
    }
}
