package dev.continuity.app.core

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class ProtocolVersionTest {

    @Test
    fun `protocol is v2`() {
        assertEquals(2, Protocol.VERSION)
        assertEquals(2, Protocol.make(Protocol.Msg.PING).getInt("v"))
    }

    @Test
    fun `v1 and missing versions are rejected instead of downgraded`() {
        for (version in listOf(1, 0, 3)) {
            try {
                Protocol.requireSupportedVersion(JSONObject().put("v", version))
                fail("envelope version $version was accepted")
            } catch (expected: IllegalArgumentException) {
                // expected
            }
        }
        try {
            Protocol.requireSupportedVersion(JSONObject())
            fail("envelope without a version was accepted")
        } catch (expected: IllegalArgumentException) {
            // expected
        }
        Protocol.requireSupportedVersion(JSONObject().put("v", 2))
    }

    @Test
    fun `frame length cap is enforced before allocation`() {
        try {
            Protocol.encode(Protocol.TYPE_JSON, ByteArray(Protocol.MAX_PAYLOAD + 1))
            fail("oversized frame was accepted")
        } catch (expected: IllegalArgumentException) {
            // expected
        }
    }
}
