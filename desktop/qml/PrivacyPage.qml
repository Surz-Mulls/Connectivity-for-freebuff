import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var status: ({})
    signal command(string name, var payload, var done)
    property var privacy: status.privacy || ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Text {
            text: "Privacy"
            color: Theme.text
            font.pixelSize: Theme.fontheadline
        }
        CheckBox {
            text: "Privacy mode (pauses clipboard, notifications and file prompts)"
            checked: !!page.privacy.privacy_mode
            onToggled: page.command("privacy.set", { privacy_mode: checked })
        }
        RowLayout {
            Text { text: "Clipboard direction"; color: Theme.text }
            ComboBox {
                model: ["off", "to_phone", "to_desktop", "both"]
                currentIndex: Math.max(0, ["off", "to_phone", "to_desktop", "both"]
                                              .indexOf(page.privacy.clipboard_direction))
                onActivated: page.command("privacy.set", { clipboard_direction: currentText })
            }
        }
        CheckBox {
            text: "Allow sensitive clipboard content (verification codes, passwords)"
            checked: !!page.privacy.clipboard_allow_sensitive
            onToggled: page.command("settings.set",
                { settings: { clipboard_allow_sensitive: checked } })
        }
        CheckBox {
            text: "Include sensitive notification content"
            checked: !!page.privacy.notifications_include_sensitive
            onToggled: page.command("settings.set",
                { settings: { notifications_include_sensitive: checked } })
        }
        CheckBox {
            text: "Auto-accept incoming files (not recommended)"
            checked: !!page.privacy.files_auto_accept
            onToggled: page.command("settings.set", { settings: { files_auto_accept: checked } })
        }
        CheckBox {
            text: "Enable ADB integration for DeX Workspace (privileged, off by default)"
            checked: !!page.privacy.adb_enabled
            onToggled: page.command("settings.set", { settings: { adb_enabled: checked } })
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Theme.overlay0
            font.pixelSize: Theme.fontcaption
            text: "Sensitive notifications on Android 15 are redacted unless you explicitly grant "
                  + "RECEIVE_SENSITIVE_NOTIFICATIONS. This app never runs that command for you."
        }
        Item { Layout.fillHeight: true }
    }
}
