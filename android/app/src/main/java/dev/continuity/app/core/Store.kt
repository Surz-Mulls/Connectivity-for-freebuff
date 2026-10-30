package dev.continuity.app.core

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject

/** Shared UI/state surface. Nothing here is authoritative connection state: the session is. */
object AppState {
    val status = MutableStateFlow(JSONObject())
    val pairing = MutableStateFlow<JSONObject?>(null)
    val log = MutableStateFlow<List<String>>(emptyList())

    fun note(message: String) {
        log.value = (log.value + message).takeLast(80)
    }
}

class PairingDecision(val request: JSONObject) {
    @Volatile var answered = false
    @Volatile var accepted = false
}

/** Settings + pinned fingerprints, stored in the app's private SharedPreferences. */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("continuity", Context.MODE_PRIVATE)

    var deviceName: String
        get() = prefs.getString("device_name", "") ?: ""
        set(value) = prefs.edit().putString("device_name", value.take(64)).apply()

    var clipboardEnabled: Boolean
        get() = prefs.getBoolean("clipboard_enabled", true)
        set(value) = prefs.edit().putBoolean("clipboard_enabled", value).apply()

    var clipboardDirection: String
        get() = prefs.getString("clipboard_direction", "both") ?: "both"
        set(value) = prefs.edit().putString("clipboard_direction", value).apply()

    var clipboardAllowSensitive: Boolean
        get() = prefs.getBoolean("clipboard_allow_sensitive", false)
        set(value) = prefs.edit().putBoolean("clipboard_allow_sensitive", value).apply()

    var notificationsEnabled: Boolean
        get() = prefs.getBoolean("notifications_enabled", true)
        set(value) = prefs.edit().putBoolean("notifications_enabled", value).apply()

    var notificationsIncludeSensitive: Boolean
        get() = prefs.getBoolean("notifications_include_sensitive", false)
        set(value) = prefs.edit().putBoolean("notifications_include_sensitive", value).apply()

    var privacyMode: Boolean
        get() = prefs.getBoolean("privacy_mode", false)
        set(value) = prefs.edit().putBoolean("privacy_mode", value).apply()

    var expectedFingerprintValue: String?
        get() = prefs.getString("expected_fingerprint", null)
        set(value) = prefs.edit().putString("expected_fingerprint", value).apply()

    var lastDesktop: String?
        get() = prefs.getString("last_desktop", null)
        set(value) = prefs.edit().putString("last_desktop", value).apply()

    fun expectedFingerprint(): String? = expectedFingerprintValue

    // ---------------------------------------------------------------- trust store
    private fun trustedJson(): JSONObject {
        val raw = prefs.getString("trusted", null) ?: return JSONObject()
        return runCatching { JSONObject(raw) }.getOrElse { JSONObject() }
    }

    fun isTrusted(fingerprint: String): Boolean {
        val entry = trustedJson().optJSONObject(fingerprint) ?: return false
        return !entry.optBoolean("revoked", false)
    }

    fun isRevoked(fingerprint: String): Boolean =
        trustedJson().optJSONObject(fingerprint)?.optBoolean("revoked", false) ?: false

    fun trust(fingerprint: String, name: String, deviceId: String, platform: String,
              sasDigits: String) {
        val all = trustedJson()
        all.put(
            fingerprint,
            JSONObject()
                .put("name", name.take(64))
                .put("device_id", deviceId.take(128))
                .put("platform", platform.take(32))
                .put("paired_at", java.time.Instant.now().toString())
                .put("sas", sasDigits)
                .put("revoked", false)
        )
        prefs.edit().putString("trusted", all.toString()).apply()
    }

    fun revoke(fingerprint: String) {
        val all = trustedJson()
        val entry = all.optJSONObject(fingerprint) ?: return
        entry.put("revoked", true)
        entry.put("revoked_at", java.time.Instant.now().toString())
        all.put(fingerprint, entry)
        prefs.edit().putString("trusted", all.toString()).apply()
    }

    fun trustedDevices(): List<JSONObject> {
        val all = trustedJson()
        return all.keys().asSequence().mapNotNull { key ->
            val entry = all.optJSONObject(key) ?: return@mapNotNull null
            if (entry.optBoolean("revoked", false)) null
            else entry.put("fingerprint", key)
        }.toList()
    }

    fun pendingPairings(): MutableMap<String, PairingDecision> = pending

    private val pending = mutableMapOf<String, PairingDecision>()
}
