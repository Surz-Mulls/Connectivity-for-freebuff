package dev.continuity.app.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class HandshakeTest {

    private val nonceA = ByteArray(32) { 0x11 }
    private val nonceB = ByteArray(32) { 0x22 }
    private val client = "aa".repeat(32)
    private val server = "bb".repeat(32)

    @Test
    fun `transcript is stable`() {
        val first = Handshake.transcript("client", client, server, nonceA, nonceB, server)
        val second = Handshake.transcript("client", client, server, nonceA, nonceB, server)
        assertArrayEquals(first, second)
    }

    @Test
    fun `role identity nonce and tls binding all change the transcript`() {
        val base = Handshake.transcript("client", client, server, nonceA, nonceB, server)
        assertNotEquals(
            toHex(base),
            toHex(Handshake.transcript("server", client, server, nonceA, nonceB, server))
        )
        assertNotEquals(
            toHex(base),
            toHex(Handshake.transcript("client", server, server, nonceA, nonceB, server))
        )
        assertNotEquals(
            toHex(base),
            toHex(Handshake.transcript("client", client, server, nonceB, nonceA, server))
        )
        // A relay presents its own certificate; the transcript must differ.
        assertNotEquals(
            toHex(base),
            toHex(Handshake.transcript("client", client, server, nonceA, nonceB,
                "cc".repeat(32)))
        )
    }

    @Test
    fun `fields are length prefixed so shifting bytes cannot collide`() {
        val left = Handshake.transcript("client", "aa", "bb", nonceA, nonceB, "cc")
        val right = Handshake.transcript("client", "aaa", "b", nonceA, nonceB, "cc")
        assertNotEquals(toHex(left), toHex(right))
        // LABEL ("continuity/handshake/v2") + NUL precede the first 2-byte length prefix.
        val labelLength = "continuity/handshake/v2".length + 1
        val firstFieldLength = ((left[labelLength].toInt() and 0xff) shl 8) or
            (left[labelLength + 1].toInt() and 0xff)
        assertEquals(6, firstFieldLength)
        assertEquals("client", String(left, labelLength + 2, firstFieldLength))
    }

    private fun toHex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it) }
}
