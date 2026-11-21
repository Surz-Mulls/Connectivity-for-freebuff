package dev.continuity.app.core

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject

/** Shared UI/state surface. Nothing here is authoritative connection state: the session is. */
object AppState {
    val status = MutableStateFlow(JSONObject())
    val pairing = MutableStateFlow<JSONObject?>(null)
    val log = MutableStateFlow<List<String>>(emptyList())

    /** Measured foreground state, set by [MainActivity]/onResume and onPause — never assumed. */
    @Volatile
    var activityVisible: Boolean = false

    fun note(message: String) {
        log.value = (log.value + message).takeLast(80)
    }
}

class PairingDecision(val request: JSONObject) {
    @Volatile var answered = false
    @Volatile var accepted = false
}

/**
 * A remembered desktop endpoint. Host and port are stored separately so an IPv6 literal is never
 * split on one of its own colons. [parse] exists only for the legacy combined string.
 */
data class DesktopTarget(val host: String, val port: Int) {
    init {
        require(host.isNotBlank()) { "host is blank" }
        require(port in 1..65535) { "port out of range" }
    }

    companion object {
        /**
         * Parse the old `host:port` field defensively. Bracketed IPv6 is unambiguous; a bare IPv6
         * literal is accepted with its last group as the port (the old writer always appended a
         * port). New writes never use this parser because the fields are separate.
         */
        fun parse(value: String?): DesktopTarget? {
            val text = value?.trim().orEmpty()
            if (text.isEmpty()) return null
            if (text.startsWith("[")) {
                val close = text.indexOf(']')
                if (close <= 1 || close + 1 >= text.length || text[close + 1] != ':') return null
                return fromParts(text.substring(1, close), text.substring(close + 2).toIntOrNull())
            }
            val split = text.lastIndexOf(':')
            if (split <= 0 || split == text.length - 1) return null
            return fromParts(text.substring(0, split), text.substring(split + 1).toIntOrNull())
        }

        fun fromParts(host: String?, port: Int?): DesktopTarget? {
            val cleaned = host?.trim().orEmpty()
            if (cleaned.isEmpty() || port == null || port !in 1..65535) return null
            // Brackets are display syntax; the socket wants the bare address.
            val unbracketed = if (cleaned.startsWith("[") && cleaned.endsWith("]")) {
                cleaned.substring(1, cleaned.length - 1)
            } else {
                cleaned
            }
            if (unbracketed.isBlank() || unbracketed.all { it == ':' }) return null
            return DesktopTarget(unbracketed, port)
        }
    }
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

    var filesEnabled: Boolean
        get() = prefs.getBoolean("files_enabled", true)
        set(value) = prefs.edit().putBoolean("files_enabled", value).apply()

    /**
     * Off by default on purpose. Accepting file *offers* and auto-accepting their *contents* are
     * different decisions; only this explicit opt-in skips the per-file Accept/Reject prompt, and
     * even then only for a device that is already pinned and trusted.
     */
    var filesAutoAccept: Boolean
        get() = prefs.getBoolean("files_auto_accept", false)
        set(value) = prefs.edit().putBoolean("files_auto_accept", value).apply()

    var privacyMode: Boolean
        get() = prefs.getBoolean("privacy_mode", false)
        set(value) = prefs.edit().putBoolean("privacy_mode", value).apply()

    var expectedFingerprintValue: String?
        get() = prefs.getString("expected_fingerprint", null)
        set(value) = prefs.edit().putString("expected_fingerprint", value).apply()

    /** Structured target; migrates the old combined `last_desktop` value once, on first read. */
    val lastDesktopTarget: DesktopTarget?
        get() {
            if (prefs.contains("last_desktop_host") && prefs.contains("last_desktop_port")) {
                return DesktopTarget.fromParts(
                    prefs.getString("last_desktop_host", null),
                    prefs.getInt("last_desktop_port", 0)
                )
            }
            val legacy = prefs.getString("last_desktop", null) ?: return null
            val parsed = DesktopTarget.parse(legacy) ?: return null
            rememberDesktop(parsed.host, parsed.port)
            return parsed
        }

    val lastDesktopHost: String?
        get() = lastDesktopTarget?.host

    val lastDesktopPort: Int?
        get() = lastDesktopTarget?.port

    fun rememberDesktop(host: String, port: Int) {
        val target = requireNotNull(DesktopTarget.fromParts(host, port)) {
            "invalid desktop endpoint"
        }
        prefs.edit()
            .putString("last_desktop_host", target.host)
            .putInt("last_desktop_port", target.port)
            .remove("last_desktop")
            .apply()
    }

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
