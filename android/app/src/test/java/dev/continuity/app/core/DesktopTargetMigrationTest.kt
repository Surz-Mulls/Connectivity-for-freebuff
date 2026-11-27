package dev.continuity.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

private class FakePrefs : DesktopTargetPrefs {
    val values = mutableMapOf<String, Any?>()
    var writes = 0

    override fun contains(key: String) = values.containsKey(key)
    override fun getString(key: String, fallback: String?): String? =
        values[key] as? String ?: fallback
    override fun getInt(key: String, fallback: Int): Int = values[key] as? Int ?: fallback
    override fun putString(key: String, value: String) {
        values[key] = value
        writes++
    }
    override fun putInt(key: String, value: Int) {
        values[key] = value
        writes++
    }
    override fun remove(key: String) {
        values.remove(key)
        writes++
    }
}

class DesktopTargetMigrationTest {

    @Test
    fun `legacy target migrates once and the legacy key disappears`() {
        val prefs = FakePrefs()
        prefs.values["last_desktop"] = "192.168.1.10:5555"
        prefs.values["trusted"] = """{"fp":{}}"""
        prefs.values["expected_fingerprint"] = "f".repeat(64)

        val first = readDesktopTarget(prefs)
        assertEquals(DesktopTarget("192.168.1.10", 5555), first)
        assertNull(prefs.values["last_desktop"])
        assertEquals("192.168.1.10", prefs.values["last_desktop_host"])
        assertEquals(5555, prefs.values["last_desktop_port"])

        val writesAfterMigration = prefs.writes
        val second = readDesktopTarget(prefs)
        assertEquals(first, second)
        assertEquals("the second read must not re-run migration", writesAfterMigration, prefs.writes)
        assertEquals("""{"fp":{}}""", prefs.values["trusted"])
        assertEquals("f".repeat(64), prefs.values["expected_fingerprint"])
    }

    @Test
    fun `a migrated bare IPv6 target is stable on the next read`() {
        val prefs = FakePrefs()
        prefs.values["last_desktop"] = "2001:db8::1:47820"
        assertEquals(DesktopTarget("2001:db8::1", 47820), readDesktopTarget(prefs))
        assertEquals(DesktopTarget("2001:db8::1", 47820), readDesktopTarget(prefs))
        assertNull(prefs.values["last_desktop"])
    }

    @Test
    fun `structured fields win over a stale legacy key`() {
        val prefs = FakePrefs()
        prefs.values["last_desktop"] = "10.0.0.1:1111"
        prefs.values["last_desktop_host"] = "10.0.0.2"
        prefs.values["last_desktop_port"] = 2222

        assertEquals(DesktopTarget("10.0.0.2", 2222), readDesktopTarget(prefs))
        assertEquals("10.0.0.1:1111", prefs.values["last_desktop"])
        assertEquals(0, prefs.writes)
    }

    @Test
    fun `malformed legacy value is not migrated or overwritten`() {
        val prefs = FakePrefs()
        prefs.values["last_desktop"] = "[2001:db8::1]:99999"

        assertNull(readDesktopTarget(prefs))
        assertEquals("[2001:db8::1]:99999", prefs.values["last_desktop"])
        assertFalse(prefs.values.containsKey("last_desktop_host"))
        assertEquals(0, prefs.writes)
    }

    @Test
    fun `writing a target removes the legacy key and stays idempotent`() {
        val prefs = FakePrefs()
        prefs.values["last_desktop"] = "10.0.0.1:1111"

        writeDesktopTarget(prefs, DesktopTarget("::1", 9))
        writeDesktopTarget(prefs, DesktopTarget("::1", 9))

        assertEquals(DesktopTarget("::1", 9), readDesktopTarget(prefs))
        assertNull(prefs.values["last_desktop"])
        assertEquals("::1", prefs.values["last_desktop_host"])
        assertEquals(9, prefs.values["last_desktop_port"])
    }
}
