package dev.continuity.app.core

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.fail
import org.junit.Test
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * P0 regression: the previous fixed-offset DER parser threw for every real P-256 signature.
 * Vectors are shared with the Python suite (scripts/generate-ecdsa-vectors.py).
 */
class EcdsaCodecTest {

    private fun vectors(): JSONObject {
        val stream = javaClass.getResourceAsStream("/ecdsa_vectors.json")
        assertNotNull("ecdsa_vectors.json must be on the test classpath", stream)
        return JSONObject(stream!!.reader().readText())
    }

    @Test
    fun `committed vectors convert DER to raw and back`() {
        val all = vectors().getJSONArray("valid")
        assertEquals(64, all.length())
        for (index in 0 until all.length()) {
            val vector = all.getJSONObject(index)
            val der = hex(vector.getString("der_hex"))
            val raw = hex(vector.getString("raw_hex"))
            assertArrayEquals("vector $index", raw, EcdsaCodec.derToRaw(der))
            assertArrayEquals("round trip $index", der, EcdsaCodec.rawToDer(raw))
        }
    }

    @Test
    fun `real JCA signatures always convert`() {
        val generator = KeyPairGenerator.getInstance("EC")
        generator.initialize(ECGenParameterSpec("secp256r1"))
        val keyPair = generator.generateKeyPair()
        repeat(300) { index ->
            val signer = Signature.getInstance("SHA256withECDSA")
            signer.initSign(keyPair.private)
            signer.update("continuity-$index".toByteArray())
            val der = signer.sign()
            val raw = EcdsaCodec.derToRaw(der)
            assertEquals(64, raw.size)
            assertArrayEquals(der, EcdsaCodec.rawToDer(raw))
            val verifier = Signature.getInstance("SHA256withECDSA")
            verifier.initVerify(keyPair.public)
            verifier.update("continuity-$index".toByteArray())
            assertTrue(verifier.verify(EcdsaCodec.rawToDer(raw)))
        }
    }

    @Test
    fun `malformed DER is rejected`() {
        val invalid = vectors().getJSONArray("invalid_der")
        for (index in 0 until invalid.length()) {
            try {
                EcdsaCodec.derToRaw(hex(invalid.getString(index)))
                fail("invalid DER vector $index was accepted")
            } catch (expected: IllegalArgumentException) {
                // expected
            }
        }
    }

    @Test
    fun `out of range raw scalars are rejected`() {
        val invalid = vectors().getJSONArray("invalid_raw")
        for (index in 0 until invalid.length()) {
            try {
                EcdsaCodec.rawToDer(hex(invalid.getString(index)))
                fail("invalid raw vector $index was accepted")
            } catch (expected: IllegalArgumentException) {
                // expected
            }
        }
        try {
            EcdsaCodec.rawToDer(ByteArray(63))
            fail("short raw signature was accepted")
        } catch (expected: IllegalArgumentException) {
            // expected
        }
    }

    private fun assertTrue(value: Boolean) = org.junit.Assert.assertTrue(value)

    private fun hex(value: String): ByteArray =
        ByteArray(value.length / 2) {
            ((Character.digit(value[it * 2], 16) shl 4) +
                Character.digit(value[it * 2 + 1], 16)).toByte()
        }
}
