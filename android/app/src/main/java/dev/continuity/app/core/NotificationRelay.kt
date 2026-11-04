package dev.continuity.app.core

import android.app.Notification
import android.app.RemoteInput
import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject

/**
 * Mirrors notifications to the paired desktop and executes reply actions the notification itself
 * exposes. Nothing is scraped: if an app does not publish a RemoteInput reply action, this service
 * reports that replies are unavailable instead of inventing one.
 *
 * Wiring rules (§ notification relay must actually be connected):
 * - only a currently connected, trusted desktop session receives events
 *   ([ContinuityService.trustedSession]); without one, nothing is sent and the listener survives;
 * - our own package's notifications (pairing prompts, session notices) are never mirrored;
 * - Android 15 secret-visibility notifications are reported as sensitive with their content
   dropped — text Android already redacted is never recovered;
 * - action ids are stable (`a<index>`), independent of titles that may repeat or change; replies
   verify the targeted action really carries a RemoteInput.
 */
class NotificationRelay : NotificationListenerService() {
    override fun onListenerConnected() {
        active = this
        AppState.note("notification relay connected")
    }

    override fun onListenerDisconnected() {
        if (active === this) active = null
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val service = ContinuityService.current ?: return
        val store = service.application.let { (it as dev.continuity.app.ContinuityApp).store }
        if (!store.notificationsEnabled || store.privacyMode) return
        if (sbn.packageName == service.packageName) return  // never mirror our own prompts
        val session = serviceSession() ?: return
        val notification = sbn.notification
        val extras = notification.extras
        val sensitive = notification.visibility == Notification.VISIBILITY_SECRET ||
            notification.visibility == Notification.VISIBILITY_PRIVATE
        val title: String
        val text: String
        if (notification.visibility == Notification.VISIBILITY_SECRET) {
            // Android keeps this content off the listener surface; respect it, never recover it.
            title = "Content hidden"
            text = "Notification content is not mirrored (Android secret visibility)"
        } else {
            title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
            text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
        }
        val actions = JSONArray()
        for ((index, action) in (notification.actions ?: emptyArray()).withIndex()) {
            val reply = action.remoteInputs?.any { it.resultKey != null } == true
            actions.put(
                JSONObject()
                    .put("id", "a$index")
                    .put("title", action.title?.toString() ?: "")
                    .put("reply", reply)
            )
        }
        val body = JSONObject()
            .put("key", sbn.key)
            .put("app", sbn.packageName)
            .put("title", title)
            .put("text", text)
            .put("sensitive", sensitive)
            .put("actions", actions)
        runCatching { session.send(Protocol.Msg.NOTIFY_POST, body) }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        val session = serviceSession() ?: return
        runCatching { session.send(Protocol.Msg.NOTIFY_DISMISS, JSONObject().put("key", sbn.key)) }
    }

    private fun serviceSession(): ContinuitySession? = ContinuityService.current?.trustedSession()

    companion object {
        @Volatile
        var active: NotificationRelay? = null
            private set

        /** Cancel a mirrored notification on this device (desktop-initiated dismiss). */
        fun dismiss(key: String): Boolean {
            val relay = active ?: return false
            return runCatching {
                relay.cancelNotification(key)
                true
            }.getOrDefault(false)
        }

        /** Send a reply through the notification's own RemoteInput action. */
        fun reply(key: String, actionId: String, text: String): Boolean {
            val relay = active ?: return false
            val sbn = relay.activeNotifications.firstOrNull { it.key == key } ?: return false
            val actions = sbn.notification.actions ?: return false
            fun hasRemoteInput(action: Notification.Action): Boolean =
                action.remoteInputs?.any { it.resultKey != null } == true
            val action = when {
                actionId.startsWith("a") && actionId.length > 1 ->
                    actionId.substring(1).toIntOrNull()?.takeIf { it in actions.indices }
                        ?.let { actions[it] }?.takeIf { hasRemoteInput(it) }
                        ?: actions.firstOrNull { hasRemoteInput(it) }
                else -> actions.firstOrNull { hasRemoteInput(it) }
            } ?: return false
            val remoteInput = action.remoteInputs?.firstOrNull { it.resultKey != null } ?: return false
            val intent = Intent()
            val bundle = android.os.Bundle()
            bundle.putCharSequence(remoteInput.resultKey, text)
            RemoteInput.addResultsToIntent(arrayOf(remoteInput), intent, bundle)
            return runCatching {
                action.actionIntent.send(relay, 0, intent)
                true
            }.getOrDefault(false)
        }
    }
}
