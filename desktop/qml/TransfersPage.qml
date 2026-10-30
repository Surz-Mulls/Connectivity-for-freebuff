import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var status: ({})
    signal command(string name, var payload, var done)

    ColumnLayout {
        anchors.fill: parent
        spacing: 8
        Text {
            text: "Transfers"
            color: Theme.text
            font.pixelSize: Theme.fontheadline
        }
        Text {
            Layout.fillWidth: true
            color: Theme.subtext
            font.pixelSize: Theme.fontcaption
            wrapMode: Text.WordWrap
            text: "Files are checksum-verified before they appear in the receive folder. "
                  + "Duplicate names never overwrite: a numeric suffix is chosen instead."
        }
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: page.status.transfers || []
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width
                height: 84
                radius: Theme.radiusSm
                color: Theme.surface0
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: (modelData.direction === "send" ? "↑ " : "↓ ") + modelData.name
                            color: Theme.text
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                        }
                        Text {
                            text: modelData.state + (modelData.error ? " — " + modelData.error : "")
                            color: modelData.state === "done" ? Theme.ok
                                 : modelData.state === "failed" ? Theme.error : Theme.warn
                            font.pixelSize: Theme.fontcaption
                        }
                    }
                    ProgressBar {
                        Layout.fillWidth: true
                        from: 0
                        to: 1
                        value: modelData.progress
                    }
                    Text {
                        text: Math.round(modelData.transferred / 1024) + " / "
                              + Math.round(modelData.size / 1024) + " KiB · " + modelData.peer
                        color: Theme.overlay0
                        font.pixelSize: Theme.fontcaption
                    }
                }
            }
        }
        Text {
            visible: (page.status.transfers || []).length === 0
            color: Theme.overlay0
            text: "No transfers yet."
        }
    }
}
