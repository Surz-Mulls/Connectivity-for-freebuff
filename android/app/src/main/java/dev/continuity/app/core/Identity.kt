package dev.continuity.app.core

import android.content.Context
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import java.io.File
import java.math.BigInteger
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.security.Security
import java.security.Signature
import java.security.cert.X509Certificate
import java.util.Date
import java.util.UUID

/**
 * Device identity: self-signed ECDSA P-256 certificate, generated once and stored in the app's
 * private files directory. The SHA-256 fingerprint of the DER certificate is the device identity;
 * the private key never leaves this sandbox and is never exported by diagnostics.
 */
class Identity(
    val deviceId: String,
    val name: String,
    val certificate: X509Certificate,
    private val keyPair: KeyPair,
) {
    val certDer: ByteArray get() = certificate.encoded
    val fingerprint: String get() = sha256Hex(certDer)

    /** ECDSA/SHA-256 over [data], normalised to raw r||s (64 bytes) — the desktop expects this. */
    fun sign(data: ByteArray): ByteArray {
        val signer = Signature.getInstance("SHA256withECDSA")
        signer.initSign(keyPair.private)
        signer.update(data)
        return derToRaw(signer.sign())
    }

    fun publicKey(): PublicKey = keyPair.public

    fun privateKey(): PrivateKey = keyPair.private

    companion object {
        private const val PREFS = "continuity-identity"

        fun sha256Hex(bytes: ByteArray): String =
            MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it) }

        fun loadOrCreate(context: Context, requestedName: String? = null): Identity {
            Security.removeProvider("BC")
            Security.addProvider(BouncyCastleProvider())
            val dir = File(context.filesDir, "identity").apply { mkdirs() }
            val certFile = File(dir, "device-cert.der")
            val keyFile = File(dir, "device-key.der")
            val metaFile = File(dir, "device.json")
            if (certFile.exists() && keyFile.exists() && metaFile.exists()) {
                val cert = java.security.cert.CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(certFile.inputStream()) as X509Certificate
                val keySpec = java.security.spec.PKCS8EncodedKeySpec(keyFile.readBytes())
                val privateKey: PrivateKey = java.security.KeyFactory
                    .getInstance("EC")
                    .generatePrivate(keySpec)
                val pubSpec = java.security.spec.X509EncodedKeySpec(
                    cert.publicKey.encoded
                )
                val publicKey = java.security.KeyFactory.getInstance("EC").generatePublic(pubSpec)
                val meta = org.json.JSONObject(metaFile.readText())
                return Identity(
                    meta.getString("device_id"),
                    meta.getString("name"),
                    cert,
                    KeyPair(publicKey, privateKey)
                )
            }

            val name = (requestedName ?: android.os.Build.MODEL ?: "Android").take(64)
            val deviceId = UUID.randomUUID().toString()
            val generator = KeyPairGenerator.getInstance("EC")
            generator.initialize(java.security.spec.ECGenParameterSpec("secp256r1"), SecureRandom())
            val keyPair = generator.generateKeyPair()
            val now = Date()
            val subject = X500Name("CN=Continuity $name, O=Continuity")
            val builder = JcaX509v3CertificateBuilder(
                subject,
                BigInteger(64, SecureRandom()),
                Date(now.time - 300_000),
                Date(now.time + 5L * 365 * 24 * 3600 * 1000),
                subject,
                keyPair.public
            )
            val signer = JcaContentSignerBuilder("SHA256withECDSA")
                .setProvider("BC")
                .build(keyPair.private)
            val cert = JcaX509CertificateConverter()
                .setProvider("BC")
                .getCertificate(builder.build(signer))

            certFile.writeBytes(cert.encoded)
            keyFile.writeBytes(keyPair.private.encoded)
            metaFile.writeText(
                org.json.JSONObject()
                    .put("device_id", deviceId)
                    .put("name", name)
                    .put("created", now.toInstant().toString())
                    .toString()
            )
            listOf(certFile, keyFile, metaFile).forEach { runCatching { it.setReadable(false, false) } }
            return Identity(deviceId, name, cert, keyPair)
        }

        fun verify(certDer: ByteArray, data: ByteArray, signature: ByteArray): Boolean {
            return try {
                val cert = java.security.cert.CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(certDer.inputStream()) as X509Certificate
                val verifier = Signature.getInstance("SHA256withECDSA")
                verifier.initVerify(cert.publicKey)
                verifier.update(data)
                verifier.verify(rawToDer(signature))
            } catch (e: Exception) {
                false
            }
        }

        private fun derToRaw(der: ByteArray): ByteArray {
            var index = 0
            require(der[index++] == 0x30.toByte()) { "not a DER sequence" }
            index += lengthSize(der, index) + lengthBytes(der, indexOfLength(der, 1))
            val rLength = der[index + 1].toInt()
            val r = der.copyOfRange(index + 2, index + 2 + rLength)
            index += 2 + rLength
            val sLength = der[index + 1].toInt()
            val s = der.copyOfRange(index + 2, index + 2 + sLength)
            val raw = ByteArray(64)
            copyFixed(r, raw, 0)
            copyFixed(s, raw, 32)
            return raw
        }

        private fun indexOfLength(der: ByteArray, start: Int): Int {
            var i = start
            if (der[i].toInt() and 0x80 != 0) i += der[i].toInt() and 0x7f
            return i + 1
        }

        private fun lengthBytes(der: ByteArray, index: Int): Int =
            if (der[index].toInt() and 0x80 != 0) der[index].toInt() and 0x7f else 0

        private fun lengthSize(der: ByteArray, index: Int): Int = lengthBytes(der, index) - 1

        private fun copyFixed(source: ByteArray, target: ByteArray, offset: Int) {
            val value = BigInteger(1, source).toByteArray()
            val trimmed = value.dropWhile { it == 0.toByte() }.toByteArray()
            require(trimmed.size <= 32) { "ECDSA scalar too large" }
            System.arraycopy(trimmed, 0, target, offset + 32 - trimmed.size, trimmed.size)
        }

        private fun rawToDer(raw: ByteArray): ByteArray {
            require(raw.size == 64) { "raw signature must be 64 bytes" }
            val r = BigInteger(1, raw.copyOfRange(0, 32))
            val s = BigInteger(1, raw.copyOfRange(32, 64))
            val rBytes = r.toByteArray()
            val sBytes = s.toByteArray()
            val total = 2 + rBytes.size + 2 + sBytes.size
            val out = ByteArray(2 + total)
            var i = 0
            out[i++] = 0x30
            out[i++] = total.toByte()
            out[i++] = 0x02
            out[i++] = rBytes.size.toByte()
            rBytes.copyInto(out, i); i += rBytes.size
            out[i++] = 0x02
            out[i++] = sBytes.size.toByte()
            sBytes.copyInto(out, i)
            return out
        }
    }
}
