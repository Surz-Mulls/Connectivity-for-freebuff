package dev.continuity.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DesktopTargetTest {

    @Test
    fun `bracketed and bare IPv6 legacy targets keep the address intact`() {
        assertEquals(DesktopTarget("::1", 9), DesktopTarget.parse("[::1]:9"))
        assertEquals(DesktopTarget("::1", 9), DesktopTarget.parse("::1:9"))
        assertEquals(DesktopTarget("2001:db8::1", 47820),
            DesktopTarget.parse("2001:db8::1:47820"))
        assertEquals(DesktopTarget("2001:db8::1", 47820),
            DesktopTarget.parse("[2001:db8::1]:47820"))
    }

    @Test
    fun `hostname and IPv4 legacy targets still parse`() {
        assertEquals(DesktopTarget("desktop.local", 47820),
            DesktopTarget.parse("desktop.local:47820"))
        assertEquals(DesktopTarget("192.168.1.20", 1716),
            DesktopTarget.parse(" 192.168.1.20:1716 "))
    }

    @Test
    fun `structured fields strip display brackets and reject invalid ports`() {
        assertEquals(DesktopTarget("::1", 9), DesktopTarget.fromParts("[::1]", 9))
        assertEquals(DesktopTarget("::1", 9), DesktopTarget.fromParts("::1", 9))
        assertNull(DesktopTarget.fromParts("", 9))
        assertNull(DesktopTarget.fromParts("   ", 9))
        assertNull(DesktopTarget.fromParts("::1", 0))
        assertNull(DesktopTarget.fromParts("::1", 65536))
        assertNull(DesktopTarget.fromParts(":", 9))
    }

    @Test
    fun `malformed legacy targets are refused instead of guessed`() {
        listOf(
            "",
            "   ",
            "desktop.local",
            "desktop.local:",
            ":47820",
            "desktop.local:not-a-port",
            "desktop.local:0",
            "desktop.local:65536",
            "[::1]",
            "[::1]:",
            "[::1]:not-a-port",
            "::1"
        ).forEach { assertNull("accepted $it", DesktopTarget.parse(it)) }
    }
}
