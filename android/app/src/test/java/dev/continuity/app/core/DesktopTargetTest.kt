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
        assertEquals(DesktopTarget("192.168.1.10", 5555),
            DesktopTarget.parse("192.168.1.10:5555"))
    }

    @Test
    fun `structured fields accept host-only IPv6 and strip display brackets`() {
        assertEquals(DesktopTarget("::1", 9), DesktopTarget.fromParts("[::1]", 9))
        assertEquals(DesktopTarget("::1", 9), DesktopTarget.fromParts("::1", 9))
        assertEquals(DesktopTarget("::1", 9), DesktopTarget.fromParts("  [::1]  ", 9))
        // Host-only form: accepted here because port is a separate argument, never through parse().
        assertEquals(DesktopTarget("2001:db8::1", 47820),
            DesktopTarget.fromParts("2001:db8::1", 47820))
        assertEquals(DesktopTarget("::ffff:192.168.1.10", 9),
            DesktopTarget.fromParts("::ffff:192.168.1.10", 9))
    }

    @Test
    fun `structured fields reject brackets whitespace and malformed IPv6`() {
        listOf(
            "[2001:db8::1",
            "2001:db8::1]",
            "[2001:db8::1]extra",
            "[[2001:db8::1]]",
            "host name",
            "host\tname",
            "::1]",
            "[::1",
            "not::ipv6",
            "1:2:3:4:5:6:7:8:9",
            "1::2::3",
            "fe80::1%eth0",
            ":",
            ":::",
            "12345::1",
            "::ffff:999.1.1.1"
        ).forEach { assertNull("accepted $it", DesktopTarget.fromParts(it, 5555)) }
        assertNull(DesktopTarget.fromParts("", 5555))
        assertNull(DesktopTarget.fromParts("   ", 5555))
        assertNull(DesktopTarget.fromParts("::1", 0))
        assertNull(DesktopTarget.fromParts("::1", 65536))
    }

    @Test
    fun `malformed legacy targets from the review are refused instead of guessed`() {
        listOf(
            "",
            "   ",
            "desktop.local",
            "desktop.local:",
            ":47820",
            "desktop.local:not-a-port",
            "desktop.local:0",
            "desktop.local:65536",
            "[2001:db8::1",
            "2001:db8::1]",
            "::1]:5555",
            "[[2001:db8::1]]:5555",
            "[2001:db8::1]extra:5555",
            "[2001:db8::1]:",
            "[2001:db8::1]:99999",
            "[::1]",
            "[::1]:",
            "[::1]:not-a-port",
            "::1",
            "2001:db8::1"
        ).forEach { assertNull("accepted $it", DesktopTarget.parse(it)) }
    }
}
