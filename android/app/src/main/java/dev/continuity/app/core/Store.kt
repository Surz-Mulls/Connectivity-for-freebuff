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

private val IPV6_GROUP = Regex("[0-9A-Fa-f]{1,4}")
private val IPV4_LITERAL = Regex("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})")

private fun isIpv4Literal(value: String): Boolean {
    val match = IPV4_LITERAL.matchEntire(value) ?: return false
    return match.groupValues.drop(1).all { it.toInt() in 0..255 }
}

/** Number of 16-bit groups in a colon-separated IPv6 half; an IPv4 tail counts as two. */
private fun ipv6Groups(part: String): Int? {
    if (part.isEmpty()) return 0
    val items = part.split(':')
    if (items.any { it.isEmpty() }) return null
    var groups = 0
    items.forEachIndexed { index, item ->
        if (item.contains('.')) {
            if (index != items.lastIndex || !isIpv4Literal(item)) return null
            groups += 2
        } else {
            if (!IPV6_GROUP.matches(item)) return null
            groups += 1
        }
    }
    return groups
}

/**
 * Strict structural IPv6 literal check: no DNS, no `java.net` fallback. A zone identifier
 * (`%eth0`) is rejected because a remembered desktop target is a routable address, not a scoped
 * link-local one.
 */
private fun isIpv6Literal(value: String): Boolean {
    if (value.isEmpty() || value.contains('%')) return false
    val first = value.indexOf("::")
    if (first < 0) return ipv6Groups(value) == 8
    if (value.indexOf("::", first + 1) >= 0) return false
    val left = ipv6Groups(value.substring(0, first)) ?: return false
    val right = ipv6Groups(value.substring(first + 2)) ?: return false
    return left + right < 8
}

/**
 * A remembered desktop endpoint. Host and port are stored separately so an IPv6 literal is never
 * split on one of its own colons. [parse] exists only for the legacy combined string.
 *
 * Asymmetry: [fromParts] accepts a host-only bare IPv6 literal such as `2001:db8::1` because the
 * port is already a separate argument. [parse] cannot: it must split a combined `host:port`, and a
 * bare IPv6 value is ambiguous (its last group looks like a port), so [parse] requires a port and
 * rejects `2001:db8::1` rather than guessing. The old writer always appended a port.
 */
data class DesktopTarget(val host: String, val port: Int) {
    init {
        require(host.isNotBlank()) { "host is blank" }
        require(port in 1..65535) { "port out of range" }
    }

    companion object {
        /**
         * Parse the old `host:port` field defensively. Bracketed IPv6 is unambiguous; a bare IPv6
         * literal is accepted with its last group as the port. Every host that survives
         * [fromParts] is a hostname, an IPv4 literal or a strict IPv6 literal. New writes never
         * use this parser because the fields are separate.
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

        /**
         * Build a target from stored fields. Brackets are display syntax and are stripped once;
         * any bracket left after that, any whitespace, and any colon-containing host that is not
         * a strict IPv6 literal is rejected instead of being handed to a socket.
         */
        fun fromParts(host: String?, port: Int?): DesktopTarget? {
            val cleaned = host?.trim().orEmpty()
            if (cleaned.isEmpty() || port == null || port !in 1..65535) return null
            val unbracketed = if (cleaned.startsWith("[") && cleaned.endsWith("]")) {
                cleaned.substring(1, cleaned.length - 1)
            } else {
                cleaned
            }
            if (unbracketed.isEmpty()) return null
            if (unbracketed.any { it == '[' || it == ']' || it.isWhitespace() }) return null
            if (unbracketed.contains(':') && !isIpv6Literal(unbracketed)) return null
            return DesktopTarget(unbracketed, port)
        }
    }
}

/** Preference surface the one-time desktop-target migration needs; fakeable in JVM tests. */
internal interface DesktopTargetPrefs {
    fun contains(key: String): Boolean
    fun getString(key: String, fallback: String?): String?
    fun getInt(key: String, fallback: Int): Int
    fun putString(key: String, value: String)
    fun putInt(key: String, value: Int)
    fun remove(key: String)
}

private const val TARGET_HOST_KEY = "last_desktop_host"
private const val TARGET_PORT_KEY = "last_desktop_port"
private const val TARGET_LEGACY_KEY = "last_desktop"

/**
 * Read the structured target, migrating the old combined `last_desktop` value at most once.
 *
 * The split keys are written before the legacy key is removed, so a later read takes the
 * structured branch and never re-runs the parser. A malformed legacy value is left untouched and
 * returns null: there is nothing safe to migrate, and the rest of the store is never modified.
 */
internal fun readDesktopTarget(prefs: DesktopTargetPrefs): DesktopTarget? {
    if (prefs.contains(TARGET_HOST_KEY) && prefs.contains(TARGET_PORT_KEY)) {
        return DesktopTarget.fromParts(
            prefs.getString(TARGET_HOST_KEY, null),
            prefs.getInt(TARGET_PORT_KEY, 0)
        )
    }
    val legacy = prefs.getString(TARGET_LEGACY_KEY, null) ?: return null
    val parsed = DesktopTarget.parse(legacy) ?: return null
    writeDesktopTarget(prefs, parsed)
    return parsed
}

internal fun writeDesktopTarget(prefs: DesktopTargetPrefs, target: DesktopTarget) {
    prefs.putString(TARGET_HOST_KEY, target.host)
    prefs.putInt(TARGET_PORT_KEY, target.port)
    prefs.remove(TARGET_LEGACY_KEY)
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

    private val targetPrefs = object : DesktopTargetPrefs {
        override fun contains(key: String) = prefs.contains(key)
        override fun getString(key: String, fallback: String?) = prefs.getString(key, fallback)
        override fun getInt(key: String, fallback: Int) = prefs.getInt(key, fallback)
        override fun putString(key: String, value: String) {
            prefs.edit().putString(key, value).apply()
        }
        override fun putInt(key: String, value: Int) {
            prefs.edit().putInt(key, value).apply()
        }
        override fun remove(key: String) {
            prefs.edit().remove(key).apply()
        }
    }

    /** Structured target; migrates the old combined `last_desktop` value once, on first read. */
    val lastDesktopTarget: DesktopTarget?
        get() = readDesktopTarget(targetPrefs)

    val lastDesktopHost: String?
        get() = lastDesktopTarget?.host

    val lastDesktopPort: Int?
        get() = lastDesktopTarget?.port

    fun rememberDesktop(host: String, port: Int) {
        val target = requireNotNull(DesktopTarget.fromParts(host, port)) {
            "invalid desktop endpoint"
        }
        writeDesktopTarget(targetPrefs, target)
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
