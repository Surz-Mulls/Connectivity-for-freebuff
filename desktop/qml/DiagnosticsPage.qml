import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var status: ({})
    signal command(string name, var payload, var done)
    property var report: ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "Diagnostics"
                color: Theme.text
                font.pixelSize: Theme.fontheadline
                Layout.fillWidth: true
            }
            Button {
                text: "Run full diagnostics"
                onClicked: page.command("diagnostics.run", null, function (result) {
                    page.report = result
                })
            }
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Theme.subtext
            font.pixelSize: Theme.fontcaption
            text: page.report.paths
                ? "Exported to " + page.report.paths.markdown + " (sanitized; no clipboard or "
                  + "notification bodies, no keys)."
                : "Runs read-only checks and writes a sanitized JSON + Markdown report. "
                  + "Checks that need the phone are reported as blocked, never as passed."
        }
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: page.report.report ? page.report.report.checks : []
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width
                height: detail.implicitHeight + 26
                radius: Theme.radiusSm
                color: Theme.surface0
                Column {
                    id: detail
                    anchors.fill: parent
                    anchors.margins: 8
                    Text {
                        text: modelData.status.toUpperCase() + " · " + modelData.id
                        color: modelData.status === "pass" ? Theme.ok
                             : modelData.status === "fail" ? Theme.error
                             : modelData.status === "blocked" ? Theme.overlay0 : Theme.warn
                        font.pixelSize: Theme.fontcaption
                        font.bold: true
                    }
                    Text {
                        width: detail.width
                        wrapMode: Text.WordWrap
                        text: modelData.title + " — " + modelData.detail
                        color: Theme.text
                        font.pixelSize: Theme.fontbody
                    }
                    Text {
                        width: detail.width
                        visible: !!modelData.remediation
                        wrapMode: Text.WordWrap
                        text: modelData.remediation
                        color: Theme.subtext
                        font.pixelSize: Theme.fontcaption
                    }
                }
            }
        }
    }
}
