package dev.continuity.app.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/**
 * P0 regression: `setReadable(false, false)` made the owner's own key unreadable, so the second
 * start of the app threw `Permission denied` while loading the identity.
 */
class IdentityPersistenceTest {

    @get:Rule
    val temporary = TemporaryFolder()

    @Test
    fun `identity survives a simulated restart and can still sign`() {
        val directory = File(temporary.root, "identity")
        val first = Identity.loadOrCreate(directory, "Pixel Test")
        assertTrue(first.fingerprint.length == 64)
        assertTrue(File(directory, "device-key.der").canRead())

        // Fresh object graph, same files, as if the process had been killed and restarted.
        val second = Identity.loadOrCreate(directory, null)
        assertEquals(first.deviceId, second.deviceId)
        assertEquals(first.fingerprint, second.fingerprint)

        val message = "cross-restart handshake".toByteArray()
        val signature = second.sign(message)
        assertEquals(64, signature.size)
        assertTrue(Identity.verify(first.certDer, message, signature))
        assertArrayEquals(first.certDer, second.certDer)
    }

    @Test
    fun `a tampered signature and a foreign certificate are rejected`() {
        val one = Identity.loadOrCreate(File(temporary.root, "one"), "One")
        val two = Identity.loadOrCreate(File(temporary.root, "two"), "Two")
        val message = "hello".toByteArray()
        val signature = one.sign(message).copyOf()
        signature[63] = (signature[63].toInt() xor 0x01).toByte()
        assertTrue(!Identity.verify(one.certDer, message, signature))
        assertTrue(!Identity.verify(two.certDer, message, one.sign(message)))
    }
}
