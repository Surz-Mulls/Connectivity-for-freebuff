import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var status: ({})
    signal command(string name, var payload, var done)
    property var probe: ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Text {
            text: "DeX Workspace"
            color: Theme.text
            font.pixelSize: Theme.fontheadline
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Theme.subtext
            font.pixelSize: Theme.fontbody
            text: "DeX mode is a first-class experience, not a mirror button. It is disabled until "
                  + "you enable the ADB integration in Privacy, because it drives your phone through "
                  + "adb/scrcpy. Native Android desktop mode is never assumed on Android 15."
        }
        RowLayout {
            spacing: 8
            Button {
                text: "Probe capabilities"
                onClicked: page.command("dex.probe", null, function (result) { page.probe = result })
            }
            Button {
                text: "Start virtual display"
                enabled: page.status.privacy && page.status.privacy.adb_enabled
                onClicked: page.command("dex.start", { mode: "virtual_display" })
            }
            Button {
                text: "Start mirror"
                enabled: page.status.privacy && page.status.privacy.adb_enabled
                onClicked: page.command("dex.start", { mode: "mirror" })
            }
            Button {
                text: "Stop session"
                onClicked: page.command("dex.stop")
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusMd
            color: Theme.mantle
            ScrollView {
                anchors.fill: parent
                anchors.margins: 12
                TextArea {
                    readOnly: true
                    wrapMode: Text.WrapAnywhere
                    color: Theme.text
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fontcaption
                    text: JSON.stringify({ session: page.status.dex ? page.status.dex.session : null,
                                           probe: page.probe }, null, 2)
                }
            }
        }
    }
}
