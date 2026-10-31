package dev.continuity.app.core

import java.math.BigInteger

/**
 * Strict conversion between ASN.1 DER ECDSA signatures and the fixed 64-byte `r || s` wire format.
 *
 * The protocol uses `r || s` (32 bytes each, big-endian). `Signature.getInstance("SHA256withECDSA")`
 * returns DER, so every signature must be converted. The previous implementation used fixed byte
 * offsets (`der[3]`, `der[5]`), which throws for essentially every real P-256 signature because DER
 * length bytes and sign-padding vary. This parser walks the actual DER structure instead.
 */
object EcdsaCodec {

    /** Order of the P-256 group; valid scalars are 1..n-1. */
    private val CURVE_ORDER =
        BigInteger("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)

    /** @throws IllegalArgumentException for malformed DER, negative/zero/out-of-range integers. */
    fun derToRaw(der: ByteArray): ByteArray {
        val outer = DerReader(der)
        val sequence = outer.readConstructed(0x30)
        val r = sequence.readInteger()
        val s = sequence.readInteger()
        sequence.requireEnd()
        outer.requireEnd()
        return encodeRaw(r, s)
    }

    /** @throws IllegalArgumentException unless [raw] is 64 bytes and both scalars are in 1..n-1. */
    fun rawToDer(raw: ByteArray): ByteArray {
        require(raw.size == 64) { "raw signature must be 64 bytes" }
        val r = BigInteger(1, raw.copyOfRange(0, 32))
        val s = BigInteger(1, raw.copyOfRange(32, 64))
        return encodeDer(r, s)
    }

    private fun encodeRaw(r: BigInteger, s: BigInteger): ByteArray {
        require(r.signum() > 0 && r < CURVE_ORDER) { "r out of range" }
        require(s.signum() > 0 && s < CURVE_ORDER) { "s out of range" }
        val out = ByteArray(64)
        writeFixed(r, out, 0)
        writeFixed(s, out, 32)
        return out
    }

    private fun encodeDer(r: BigInteger, s: BigInteger): ByteArray {
        require(r.signum() > 0 && r < CURVE_ORDER) { "r out of range" }
        require(s.signum() > 0 && s < CURVE_ORDER) { "s out of range" }
        val body = derInteger(r) + derInteger(s)
        return byteArrayOf(0x30) + derLength(body.size) + body
    }

    private fun derInteger(value: BigInteger): ByteArray {
        // BigInteger.toByteArray() is already the minimal two's-complement form: it adds a 0x00
        // sign byte exactly when the high bit is set, which is what DER requires.
        val bytes = value.toByteArray()
        return byteArrayOf(0x02) + derLength(bytes.size) + bytes
    }

    private fun derLength(length: Int): ByteArray = when {
        length < 0x80 -> byteArrayOf(length.toByte())
        length <= 0xFF -> byteArrayOf(0x81.toByte(), length.toByte())
        else -> byteArrayOf(0x82.toByte(), (length ushr 8).toByte(), length.toByte())
    }

    private fun writeFixed(value: BigInteger, target: ByteArray, offset: Int) {
        val raw = value.toByteArray()
        val bytes = if (raw.size == 33 && raw[0] == 0.toByte()) raw.copyOfRange(1, raw.size) else raw
        require(bytes.size <= 32) { "ECDSA scalar wider than 32 bytes" }
        System.arraycopy(bytes, 0, target, offset + 32 - bytes.size, bytes.size)
    }

    private class DerReader(
        private val data: ByteArray,
        private var position: Int = 0,
        private val end: Int = data.size,
    ) {
        fun readConstructed(tag: Int): DerReader {
            require(readByte() == tag) { "unexpected DER tag" }
            val length = readLength()
            require(length > 0 && position + length <= end) { "truncated DER value" }
            val inner = DerReader(data, position, position + length)
            position += length
            return inner
        }

        fun readInteger(): BigInteger {
            require(readByte() == 0x02) { "expected DER INTEGER" }
            val length = readLength()
            require(length in 1..33 && position + length <= end) { "bad INTEGER length" }
            val value = data.copyOfRange(position, position + length)
            position += length
            require(value[0].toInt() and 0x80 == 0) { "negative INTEGER" }
            require(!(value.size > 1 && value[0] == 0.toByte() && value[1].toInt() and 0x80 == 0)) {
                "non-minimal INTEGER"
            }
            return BigInteger(1, value)
        }

        fun requireEnd() {
            require(position == end) { "trailing bytes in DER value" }
        }

        private fun readByte(): Int {
            require(position < end) { "truncated DER" }
            return data[position++].toInt() and 0xff
        }

        private fun readLength(): Int {
            val first = readByte()
            if (first and 0x80 == 0) return first
            val count = first and 0x7f
            require(count in 1..2 && position + count <= end) { "unsupported DER length" }
            var value = 0
            repeat(count) { value = (value shl 8) or readByte() }
            require(value >= 0x80) { "non-minimal DER length" }
            return value
        }
    }
}
