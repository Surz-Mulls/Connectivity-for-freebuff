package dev.continuity.app.core

import android.content.Context
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
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
 *
 * The identity directory lives under `Context.filesDir`, which Android already makes unreadable to
 * other apps. Do **not** call `File.setReadable(false, false)` here: it clears the owner's read bit
 * too, so every later start failed with `Permission denied` when loading the key.
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
        return EcdsaCodec.derToRaw(signer.sign())
    }

    fun publicKey(): PublicKey = keyPair.public

    fun privateKey(): PrivateKey = keyPair.private

    companion object {
        private const val CERT_FILE = "device-cert.der"
        private const val KEY_FILE = "device-key.der"
        private const val META_FILE = "device.json"

        fun sha256Hex(bytes: ByteArray): String =
            MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it) }

        fun loadOrCreate(context: Context, requestedName: String? = null): Identity =
            loadOrCreate(File(context.filesDir, "identity"), requestedName ?: android.os.Build.MODEL)

        /**
         * JVM-testable overload. Reads an existing identity from [directory] or creates one there.
         * The private key is written with the process default permissions; the containing directory
         * is the security boundary.
         */
        fun loadOrCreate(directory: File, requestedName: String?): Identity {
            Security.removeProvider("BC")
            Security.addProvider(BouncyCastleProvider())
            directory.mkdirs()
            val certFile = File(directory, CERT_FILE)
            val keyFile = File(directory, KEY_FILE)
            val metaFile = File(directory, META_FILE)

            if (certFile.exists() && keyFile.exists() && metaFile.exists()) {
                val cert = java.security.cert.CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(certFile.inputStream()) as X509Certificate
                val privateKey: PrivateKey = java.security.KeyFactory
                    .getInstance("EC")
                    .generatePrivate(java.security.spec.PKCS8EncodedKeySpec(keyFile.readBytes()))
                val publicKey = java.security.KeyFactory
                    .getInstance("EC")
                    .generatePublic(java.security.spec.X509EncodedKeySpec(cert.publicKey.encoded))
                val meta = org.json.JSONObject(metaFile.readText())
                return Identity(
                    meta.getString("device_id"),
                    meta.getString("name"),
                    cert,
                    KeyPair(publicKey, privateKey)
                )
            }

            val name = (requestedName?.takeIf { it.isNotBlank() } ?: "Android").take(64)
            val deviceId = UUID.randomUUID().toString()
            val generator = KeyPairGenerator.getInstance("EC")
            generator.initialize(java.security.spec.ECGenParameterSpec("secp256r1"), SecureRandom())
            val keyPair = generator.generateKeyPair()
            val now = Date()
            val subject = X500Name("CN=Continuity ${name.replace(",", " ")}, O=Continuity")
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
                verifier.verify(EcdsaCodec.rawToDer(signature))
            } catch (e: Exception) {
                false
            }
        }
    }
}
