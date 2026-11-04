package dev.continuity.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Bounded exponential backoff for automatic reconnect (§ reconnection policy). */
class ReconnectPolicyTest {
    private val policy = ReconnectPolicy(baseDelayMs = 1_000, maxDelayMs = 60_000, maxAttempts = 10)

    @Test
    fun `delays double and are bounded`() {
        val delays = (1..8).map { policy.delayFor(it) }
        assertEquals(listOf(1_000L, 2_000L, 4_000L, 8_000L, 16_000L, 32_000L, 60_000L, 60_000L), delays)
        assertEquals(60_000L, policy.delayFor(50))
    }

    @Test
    fun `series is bounded by maxAttempts`() {
        assertFalse(policy.exhausted(9))
        assertTrue(policy.exhausted(10))
    }

    @Test
    fun `jitter stays within twenty percent`() {
        val base = 10_000L
        repeat(200) {
            val delayed = policy.withinJitter(base)
            assertTrue(delayed >= 8_000L && delayed <= 12_000L)
        }
        assertEquals(0L, policy.withinJitter(0))
    }

    @Test
    fun `rejects impossible configurations and attempts`() {
        try {
            ReconnectPolicy(baseDelayMs = 0)
            throw AssertionError("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
        }
        try {
            policy.delayFor(0)
            throw AssertionError("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
        }
    }

    @Test
    fun `delayFor never exceeds maxDelay with large attempts`() {
        repeat(30) { assertTrue(policy.delayFor(it + 1) <= policy.maxDelayMs) }
    }
}
