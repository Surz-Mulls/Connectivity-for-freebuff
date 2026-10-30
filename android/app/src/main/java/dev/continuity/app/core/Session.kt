package dev.continuity.app.core

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.Socket
import java.security.SecureRandom
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.SSLSocket

class PeerInfo(
    val device: JSONObject,
    val certDer: ByteArray,
    val fingerprint: String,
    var trusted: Boolean,
    val sas: JSONObject?
) {
    val name: String get() = device.optString("name", device.optString("id", "device"))
    val caps: Set<String>
        get() {
            val array = device.optJSONArray("caps") ?: JSONArray()
            return (0 until array.length()).map { array.getString(it) }.toSet()
        }

    fun public(): JSONObject = JSONObject()
        .put("id", device.optString("id"))
        .put("name", name)
        .put("platform", device.optString("platform"))
        .put("fingerprint", fingerprint)
        .put("trusted", trusted)
        .put("caps", JSONArray(caps.toList()))
}

/**
 * One authenticated session. TLS gives confidentiality; the peer is authenticated by pinned
 * fingerprint plus an ECDSA signature over both nonces (the desktop does the same).
 */
class ContinuitySession(
    private val identity: Identity,
    private val store: Store,
    private val socket: Socket,
    private val initiator: Boolean,
    private val handler: (ContinuitySession, JSONObject) -> JSONObject?,
    private val blobHandler: (ContinuitySession, JSONObject, ByteArray) -> Unit,
    private val approver: suspend (JSONObject) -> Boolean,
    private val onReady: (ContinuitySession) -> Unit,
    private val onClosed: (ContinuitySession, String?) -> Unit
) {
    @Volatile var peer: PeerInfo? = null
    @Volatile private var running = true
    private var input: InputStream? = null
    private var output: OutputStream? = null
    private val pending = ConcurrentHashMap<String, ArrayBlockingQueue<JSONObject>>()
    private var thread: Thread? = null

    fun start() {
        thread = Thread({ run() }, "continuity-session").apply { isDaemon = true }.also { it.start() }
    }

    fun stop() {
        running = false
        runCatching { socket.close() }
    }

    private fun run() {
        var failure: String? = null
        try {
            val ssl = socket as SSLSocket
            ssl.soTimeout = 30_000
            ssl.startHandshake()
            input = ssl.inputStream
            output = ssl.outputStream
            if (initiator) clientHandshake() else serverHandshake()
            onReady(this)
            loop()
        } catch (exc: Exception) {
            failure = "${exc.javaClass.simpleName}: ${exc.message}"
        } finally {
            running = false
            runCatching { socket.close() }
            onClosed(this, failure)
        }
    }

    // ------------------------------------------------------------------ handshake
    private fun serverHandshake() {
        val serverNonce = nonce()
        writeJson(
            Protocol.make(
                Protocol.Msg.HELLO_CHALLENGE,
                JSONObject()
                    .put("proto", Protocol.VERSION)
                    .put("nonce", Protocol.b64(serverNonce))
                    .put("device", deviceInfo())
                    .put("cert", Protocol.b64(identity.certDer))
            )
        )
        val hello = readJson() ?: throw IOException("no hello")
        val body = hello.getJSONObject("body")
        val clientNonce = Protocol.unb64(body.getString("nonce"))
        val certDer = Protocol.unb64(body.getString("cert"))
        val signature = Protocol.unb64(body.getString("sig"))
        if (!Identity.verify(certDer, clientNonce + serverNonce, signature)) {
            throw SecurityException("client signature invalid")
        }
        val device = body.getJSONObject("device")
        val fingerprint = Identity.sha256Hex(certDer)
        if (store.isRevoked(fingerprint)) {
            sendError("identity.revoked", "this device was revoked")
            throw SecurityException("revoked peer")
        }
        val trusted = store.isTrusted(fingerprint)
        val sas = if (trusted) null else deriveSas(fingerprint, identity.fingerprint,
            clientNonce, serverNonce)
        peer = PeerInfo(device, certDer, fingerprint, trusted, sas)
        writeJson(
            Protocol.make(
                Protocol.Msg.HELLO_OK,
                JSONObject()
                    .put("trusted", trusted)
                    .put("device", deviceInfo())
                    .put("cert", Protocol.b64(identity.certDer))
                    .put("sig", Protocol.b64(identity.sign(serverNonce + clientNonce)))
                    .put("sas", sas ?: JSONObject.NULL)
            )
        )
        if (!trusted) serverPair()
    }

    private fun serverPair() {
        val info = peer ?: throw IOException("no peer")
        val sas = info.sas ?: throw IOException("no sas")
        val approved = runBlocking { approver(info.public().put("sas", sas)) }
        if (!approved) {
            sendError("pairing.timeout", "pairing was not approved")
            throw SecurityException("pairing declined")
        }
        val msg = readJson() ?: throw IOException("pairing aborted")
        when (msg.getString("type")) {
            Protocol.Msg.PAIR_REJECT -> throw SecurityException("peer rejected pairing")
            Protocol.Msg.PAIR_CONFIRM -> {
                val body = msg.getJSONObject("body")
                if (!sasMatches(sas, body)) {
                    sendError("pairing.mismatch", "confirmation did not match")
                    throw SecurityException("sas mismatch")
                }
                store.trust(info.fingerprint, info.name, info.device.optString("id"),
                    info.device.optString("platform"), sas.optString("digits"))
                info.trusted = true
                writeJson(
                    Protocol.make(
                        Protocol.Msg.PAIR_CONFIRM,
                        JSONObject()
                            .put("sas_digits", sas.getString("digits"))
                            .put("sas_emoji", sas.getJSONArray("emoji"))
                    )
                )
            }
            else -> throw IOException("expected pair.confirm")
        }
    }

    private fun clientHandshake() {
        val challenge = readJson() ?: throw IOException("no hello.challenge")
        val body = challenge.getJSONObject("body")
        val serverNonce = Protocol.unb64(body.getString("nonce"))
        val serverCert = Protocol.unb64(body.getString("cert"))
        val serverFingerprint = Identity.sha256Hex(serverCert)
        val expected = store.expectedFingerprint()
        if (expected != null && expected != serverFingerprint) {
            throw SecurityException("desktop fingerprint does not match the pin")
        }
        val serverDevice = body.getJSONObject("device")
        val clientNonce = nonce()
        writeJson(
            Protocol.make(
                Protocol.Msg.HELLO,
                JSONObject()
                    .put("proto", Protocol.VERSION)
                    .put("nonce", Protocol.b64(clientNonce))
                    .put("device", deviceInfo())
                    .put("cert", Protocol.b64(identity.certDer))
                    .put("sig", Protocol.b64(identity.sign(clientNonce + serverNonce)))
            )
        )
        val ok = readJson() ?: throw IOException("no hello.ok")
        if (ok.getString("type") == Protocol.Msg.ERROR) {
            throw SecurityException(ok.getJSONObject("body").optString("code"))
        }
        if (!Identity.verify(serverCert, serverNonce + clientNonce,
                Protocol.unb64(ok.getJSONObject("body").getString("sig")))
        ) {
            throw SecurityException("server signature invalid")
        }
        val sas = deriveSas(identity.fingerprint, serverFingerprint, clientNonce, serverNonce)
        val trusted = store.isTrusted(serverFingerprint)
        peer = PeerInfo(serverDevice, serverCert, serverFingerprint, trusted, if (trusted) null else sas)
        if (trusted) return
        val approved = runBlocking { approver(peer!!.public().put("sas", sas)) }
        if (!approved) {
            writeJson(Protocol.make(Protocol.Msg.PAIR_REJECT, JSONObject().put("reason", "declined")))
            throw SecurityException("pairing declined")
        }
        writeJson(
            Protocol.make(
                Protocol.Msg.PAIR_CONFIRM,
                JSONObject().put("sas_digits", sas.getString("digits"))
                    .put("sas_emoji", sas.getJSONArray("emoji"))
            )
        )
        val confirm = readJson() ?: throw IOException("pairing aborted")
        if (confirm.getString("type") != Protocol.Msg.PAIR_CONFIRM ||
            !sasMatches(sas, confirm.getJSONObject("body"))
        ) {
            throw SecurityException("confirmation did not match")
        }
        store.trust(serverFingerprint, serverDevice.optString("name", "desktop"),
            serverDevice.optString("id"), serverDevice.optString("platform"),
            sas.getString("digits"))
        peer!!.trusted = true
    }

    // ------------------------------------------------------------------ loop
    private fun loop() {
        val stream = input ?: return
        while (running) {
            val frame = Protocol.readFrame(stream) ?: break
            val (type, payload) = frame
            if (type == Protocol.TYPE_JSON) {
                val msg = JSONObject(String(payload))
                val replyTo = msg.optString("reply_to", "")
                if (replyTo.isNotEmpty()) {
                    pending.remove(replyTo)?.offer(msg)
                    continue
                }
                when (msg.getString("type")) {
                    Protocol.Msg.PING -> {
                        writeJson(Protocol.reply(Protocol.Msg.PONG, msg.getString("id"),
                            JSONObject().put("ts", msg.optString("ts"))))
                        continue
                    }
                    Protocol.Msg.BYE -> return
                }
                val result = handler(this, msg)
                if (result != null) {
                    val replyType = replyTypeFor(msg.getString("type"))
                    writeJson(Protocol.reply(replyType, msg.getString("id"), result))
                }
            } else {
                val (header, data) = Protocol.decodeBlob(payload)
                blobHandler(this, header, data)
            }
        }
    }

    fun request(type: String, body: JSONObject, timeoutMs: Long = 30_000): JSONObject? {
        val envelope = Protocol.make(type, body)
        val queue = ArrayBlockingQueue<JSONObject>(1)
        pending[envelope.getString("id")] = queue
        return try {
            writeJson(envelope)
            queue.poll(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (exc: Exception) {
            null
        } finally {
            pending.remove(envelope.getString("id"))
        }
    }

    fun send(type: String, body: JSONObject) {
        writeJson(Protocol.make(type, body))
    }

    fun sendBlob(header: JSONObject, data: ByteArray) {
        val out = output ?: return
        Protocol.writeFrame(out, Protocol.TYPE_BLOB, Protocol.blob(header, data))
    }

    fun sendError(code: String, message: String) {
        runCatching { writeJson(Protocol.make(Protocol.Msg.ERROR, Protocol.error(code, message))) }
    }

    private fun writeJson(obj: JSONObject) {
        val out = output ?: throw IOException("session is not open")
        synchronized(this) { Protocol.writeJson(out, obj) }
    }

    private fun readJson(): JSONObject? {
        val stream = input ?: return null
        while (true) {
            val frame = Protocol.readFrame(stream) ?: return null
            if (frame.first == Protocol.TYPE_JSON) return JSONObject(String(frame.second))
        }
    }

    private fun deviceInfo(): JSONObject = JSONObject()
        .put("id", identity.deviceId)
        .put("name", store.deviceName.ifBlank { identity.name })
        .put("platform", "android")
        .put("app_version", "0.1.0")
        .put("proto", Protocol.VERSION)
        .put("caps", JSONArray(Protocol.Caps.androidDefault))

    private fun nonce(): ByteArray = ByteArray(32).also { SecureRandom().nextBytes(it) }

    private fun sasMatches(sas: JSONObject, body: JSONObject): Boolean {
        if (body.optString("sas_digits") != sas.getString("digits")) return false
        val local = sas.getJSONArray("emoji")
        val remote = body.optJSONArray("sas_emoji") ?: return false
        if (local.length() != remote.length()) return false
        for (index in 0 until local.length()) {
            if (local.getString(index) != remote.getString(index)) return false
        }
        return true
    }

    companion object {
        private val EMOJI = listOf(
            "🍎", "🐝", "🌙", "🚀", "🐢", "🌻", "🍀", "🎲",
            "🔑", "⭐", "🎈", "🐸", "🌵", "🍩", "🎧", "🦊",
            "🍇", "🚲", "🕯️", "🐧", "🌊", "🍄", "🦉", "🎯",
            "🧭", "🍒", "🐬", "🔔", "🌶️", "🪁", "🧩", "🎵"
        )

        fun deriveSas(clientFingerprint: String, serverFingerprint: String,
                      clientNonce: ByteArray, serverNonce: ByteArray): JSONObject {
            val ikm = hexToBytes(clientFingerprint) + hexToBytes(serverFingerprint)
            val material = hkdf(ikm, clientNonce + serverNonce, "continuity/sas/v1".toByteArray(), 8)
            val number = ((material[0].toLong() and 0xff) shl 24 or
                ((material[1].toLong() and 0xff) shl 16) or
                ((material[2].toLong() and 0xff) shl 8) or
                (material[3].toLong() and 0xff)) % 1_000_000
            val emoji = JSONArray()
            for (index in 4..7) emoji.put(EMOJI[(material[index].toInt() and 0xff) % EMOJI.size])
            return JSONObject()
                .put("digits", number.toString().padStart(6, '0'))
                .put("emoji", emoji)
        }

        private fun hkdf(ikm: ByteArray, salt: ByteArray, info: ByteArray, length: Int): ByteArray {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(salt, "HmacSHA256"))
            val prk = mac.doFinal(ikm)
            mac.init(SecretKeySpec(prk, "HmacSHA256"))
            val out = ByteArray(length)
            var block = ByteArray(0)
            var position = 0
            var counter = 1
            while (position < length) {
                mac.reset()
                mac.update(block)
                mac.update(info)
                mac.update(counter.toByte())
                block = mac.doFinal()
                val take = minOf(block.size, length - position)
                System.arraycopy(block, 0, out, position, take)
                position += take
                counter++
            }
            return out
        }

        private fun hexToBytes(hex: String): ByteArray =
            ByteArray(hex.length / 2) {
                ((Character.digit(hex[it * 2], 16) shl 4) +
                    Character.digit(hex[it * 2 + 1], 16)).toByte()
            }

        fun replyTypeFor(type: String): String = when (type) {
            Protocol.Msg.CLIPBOARD_SET -> Protocol.Msg.CLIPBOARD_ACK
            Protocol.Msg.FILE_OFFER -> Protocol.Msg.FILE_ACCEPT
            Protocol.Msg.FILE_DONE -> Protocol.Msg.FILE_RESULT
            Protocol.Msg.HANDOFF_URL -> Protocol.Msg.HANDOFF_RESULT
            Protocol.Msg.STATUS_REQUEST -> Protocol.Msg.STATUS
            Protocol.Msg.PAIR_CONFIRM -> Protocol.Msg.PAIR_CONFIRM
            else -> type
        }
    }
}
