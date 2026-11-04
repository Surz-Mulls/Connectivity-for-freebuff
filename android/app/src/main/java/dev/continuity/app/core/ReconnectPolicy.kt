package dev.continuity.app.core

import kotlin.random.Random

/**
 * Pure policy for the phone-side automatic reconnect (§ reconnection and link lifecycle).
 *
 * After a trusted initiator session to the last paired desktop drops, ContinuityService retries
 * with bounded exponential backoff plus jitter. The pinned fingerprint requirement is unchanged:
 * reconnecting never re-pairs and never accepts a replacement identity, and `maxAttempts` bounds
 * the series so a powered-off laptop cannot produce an endless wake-lock loop.
 *
 * Kept free of Android classes so it is fully unit-testable on the JVM.
 */
class ReconnectPolicy(
    val baseDelayMs: Long = 1_000,
    val maxDelayMs: Long = 60_000,
    val maxAttempts: Int = 10,
) {
    init {
        require(baseDelayMs > 0 && maxDelayMs >= baseDelayMs && maxAttempts > 0)
    }

    fun delayFor(attempt: Int): Long {
        require(attempt >= 1) { "attempt starts at 1" }
        var delay = baseDelayMs
        repeat(attempt - 1) {
            delay = (delay * 2).coerceAtMost(maxDelayMs)
        }
        return delay.coerceAtMost(maxDelayMs)
    }

    /** ±20% jitter so simultaneous phone/laptop restarts do not synchronise their storms. */
    fun withinJitter(delay: Long): Long {
        require(delay >= 0)
        return (delay * (0.8 + 0.4 * Random.nextDouble())).toLong()
    }

    fun exhausted(attempt: Int): Boolean = attempt >= maxAttempts
}
