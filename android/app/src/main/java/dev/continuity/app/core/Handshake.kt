package dev.continuity.app.core

import java.io.ByteArrayOutputStream

/**
 * Protocol v2 handshake transcript.
 *
 * Every field is length-prefixed (2-byte big-endian) after a domain label, so `ab||c` and `a||bc`
 * can never produce the same bytes. The transcript binds:
 *
 *  * protocol version and role (`client`/`server`),
 *  * both certificate fingerprints (who is talking to whom),
 *  * both nonces (freshness, replay resistance),
 *  * the certificate the signer actually saw on its TLS connection (`tlsFpr`).
 *
 * The TLS fingerprint is what stops a TLS-terminating relay: it must present its own certificate
 * to the client, so the client's `tlsFpr` cannot equal the desktop identity it relays in-band.
 */
object Handshake {
    private const val LABEL = "continuity/handshake/v2"

    fun transcript(
        role: String,
        initiatorFingerprint: String,
        responderFingerprint: String,
        initiatorNonce: ByteArray,
        responderNonce: ByteArray,
        tlsFingerprint: String,
    ): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(LABEL.toByteArray(Charsets.UTF_8))
        out.write(0)
        out.write(field(role.toByteArray(Charsets.UTF_8)))
        out.write(field(initiatorFingerprint.toByteArray(Charsets.UTF_8)))
        out.write(field(responderFingerprint.toByteArray(Charsets.UTF_8)))
        out.write(field(initiatorNonce))
        out.write(field(responderNonce))
        out.write(field(tlsFingerprint.toByteArray(Charsets.UTF_8)))
        return out.toByteArray()
    }

    private fun field(value: ByteArray): ByteArray {
        require(value.size <= 0xFFFF) { "handshake field too large" }
        return byteArrayOf((value.size ushr 8).toByte(), value.size.toByte()) + value
    }
}
