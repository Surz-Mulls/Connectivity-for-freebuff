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
        val session = serviceSession() ?: return
        val notification = sbn.notification
        val extras = notification.extras
        val sensitive = notification.visibility == Notification.VISIBILITY_SECRET
        val actions = JSONArray()
        for (action in notification.actions ?: emptyArray()) {
            val reply = action.remoteInputs?.any { it.resultKey != null } == true
            actions.put(
                JSONObject()
                    .put("id", action.title?.toString() ?: "action")
                    .put("title", action.title?.toString() ?: "")
                    .put("reply", reply)
            )
        }
        val body = JSONObject()
            .put("key", sbn.key)
            .put("app", sbn.packageName)
            .put("title", extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: "")
            .put("text", extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: "")
            .put("sensitive", sensitive)
            .put("actions", actions)
        runCatching { session.send(Protocol.Msg.NOTIFY_POST, body) }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        val session = serviceSession() ?: return
        runCatching { session.send(Protocol.Msg.NOTIFY_DISMISS, JSONObject().put("key", sbn.key)) }
    }

    private fun serviceSession(): ContinuitySession? = null // sessions are owned by the service

    companion object {
        @Volatile
        var active: NotificationRelay? = null
            private set

        /** Send a reply through the notification's own RemoteInput action. */
        fun reply(key: String, actionId: String, text: String): Boolean {
            val relay = active ?: return false
            val sbn = relay.activeNotifications.firstOrNull { it.key == key } ?: return false
            val action = sbn.notification.actions?.firstOrNull { candidate ->
                candidate.title?.toString() == actionId && candidate.remoteInputs != null
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
