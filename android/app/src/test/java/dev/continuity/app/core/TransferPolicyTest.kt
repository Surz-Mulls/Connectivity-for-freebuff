package dev.continuity.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class TransferPolicyTest {

    @get:Rule
    val temporary = TemporaryFolder()

    @Test
    fun `only canonical UUIDs are accepted as transfer ids`() {
        assertTrue(TransferPolicy.isValidTransferId("3f2504e0-4f89-41d3-9a0c-0305e82c3301"))
        assertFalse(TransferPolicy.isValidTransferId("../../etc/passwd"))
        assertFalse(TransferPolicy.isValidTransferId("3f2504e0"))
        assertFalse(TransferPolicy.isValidTransferId(""))
        assertFalse(TransferPolicy.isValidTransferId("3f2504e0-4f89-11d3-9a0c-0305e82c3301x"))
    }

    @Test
    fun `sizes and digests are bounded`() {
        assertTrue(TransferPolicy.isValidSize(0))
        assertTrue(TransferPolicy.isValidSize(TransferPolicy.MAX_FILE_SIZE))
        assertFalse(TransferPolicy.isValidSize(-1))
        assertFalse(TransferPolicy.isValidSize(TransferPolicy.MAX_FILE_SIZE + 1))
        assertTrue(TransferPolicy.isValidDigest("a".repeat(64)))
        assertFalse(TransferPolicy.isValidDigest("a".repeat(63)))
        assertFalse(TransferPolicy.isValidDigest("z".repeat(64)))
    }

    @Test
    fun `hostile names cannot escape or become dotfiles`() {
        assertEquals("passwd", TransferPolicy.safeName("../../etc/passwd"))
        assertEquals("evil.sh", TransferPolicy.safeName("..\\\\..\\\\evil.sh"))
        assertNull(TransferPolicy.safeName(".."))
        assertNull(TransferPolicy.safeName("   "))
        assertNull(TransferPolicy.safeName("CON"))
        assertNull(TransferPolicy.safeName("nul.txt"))
        // Over-long names are truncated to the limit; absurd names are refused outright.
        val long = TransferPolicy.safeName("x".repeat(250))
        assertNotNull(long)
        assertTrue(long!!.length <= TransferPolicy.MAX_NAME)
        assertNull(TransferPolicy.safeName("x".repeat(500)))
    }

    @Test
    fun `destinations stay inside the receive directory and never overwrite`() {
        val root = temporary.newFolder("received")
        val first = TransferPolicy.uniqueDestination(root, "photo.jpg")
        assertNotNull(first)
        first!!.writeText("one")
        val second = TransferPolicy.uniqueDestination(root, "photo.jpg")
        assertEquals("photo-1.jpg", second!!.name)
        assertTrue(TransferPolicy.isInside(root, second))
        assertFalse(TransferPolicy.isInside(root, java.io.File(root, "../escape")))
        assertFalse(TransferPolicy.isInside(root, root))
    }

    @Test
    fun `digestOf streams the exact size and digest`() {
        val file = temporary.newFile("payload.bin")
        file.writeBytes(ByteArray(300_000) { (it % 251).toByte() })
        val (size, digest) = TransferPolicy.digestOf(file)
        assertEquals(300_000L, size)
        assertEquals(
            java.security.MessageDigest.getInstance("SHA-256").digest(file.readBytes())
                .joinToString("") { "%02x".format(it) },
            digest
        )
    }
}
