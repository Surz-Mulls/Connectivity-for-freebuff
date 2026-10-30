package dev.continuity.app.core

import org.json.JSONObject
import java.io.EOFException
import java.io.InputStream
import java.io.OutputStream
import java.time.Instant
import java.util.Base64
import java.util.UUID

/**
 * Wire protocol v1 (see protocol/PROTOCOL.md). Frame: u32 length | u8 type | payload.
 * The 1 MiB cap is enforced before any buffer is allocated.
 */
object Protocol {
    const val VERSION = 1
    const val MAX_PAYLOAD = 1 shl 20
    const val TYPE_JSON = 1
    const val TYPE_BLOB = 2

    object Msg {
        const val HELLO_CHALLENGE = "hello.challenge"
        const val HELLO = "hello"
        const val HELLO_OK = "hello.ok"
        const val PAIR_CONFIRM = "pair.confirm"
        const val PAIR_REJECT = "pair.reject"
        const val TRUST_REVOKE = "trust.revoke"
        const val PING = "ping"
        const val PONG = "pong"
        const val CLIPBOARD_SET = "clipboard.set"
        const val CLIPBOARD_ACK = "clipboard.ack"
        const val FILE_OFFER = "file.offer"
        const val FILE_ACCEPT = "file.accept"
        const val FILE_REJECT = "file.reject"
        const val FILE_CHUNK = "file.chunk"
        const val FILE_DONE = "file.done"
        const val FILE_RESULT = "file.result"
        const val NOTIFY_POST = "notify.post"
        const val NOTIFY_DISMISS = "notify.dismiss"
        const val NOTIFY_ACTION = "notify.action"
        const val MEDIA_STATE = "media.state"
        const val MEDIA_COMMAND = "media.command"
        const val HANDOFF_URL = "handoff.url"
        const val HANDOFF_RESULT = "handoff.result"
        const val FIND_RING = "find.ring"
        const val FIND_PING = "find.ping"
        const val STATUS = "status"
        const val STATUS_REQUEST = "status.request"
        const val PRIVACY_SET = "privacy.set"
        const val CAMERA_REQUEST = "camera.request"
        const val CAMERA_RESULT = "camera.result"
        const val DEX_PROBE = "dex.probe"
        const val DEX_SESSION = "dex.session"
        const val ERROR = "error"
        const val BYE = "bye"
    }

    object Caps {
        const val CLIPBOARD_READ = "clipboard.read"
        const val CLIPBOARD_WRITE = "clipboard.write"
        const val FILES_SEND = "files.send"
        const val FILES_RECEIVE = "files.receive"
        const val NOTIFICATIONS_MIRROR = "notifications.mirror"
        const val NOTIFICATIONS_REPLY = "notifications.reply"
        const val NOTIFICATIONS_DISMISS = "notifications.dismiss"
        const val HANDOFF_OPEN = "handoff.open"
        const val HANDOFF_SEND = "handoff.send"
        const val FIND_RING = "find.ring"
        const val FIND_PING = "find.ping"
        const val STATUS_BATTERY = "status.battery"

        val androidDefault = listOf(
            CLIPBOARD_READ, CLIPBOARD_WRITE, FILES_SEND, FILES_RECEIVE,
            NOTIFICATIONS_MIRROR, NOTIFICATIONS_REPLY, NOTIFICATIONS_DISMISS,
            HANDOFF_OPEN, HANDOFF_SEND, FIND_RING, FIND_PING, STATUS_BATTERY
        )
    }

    fun make(type: String, body: JSONObject = JSONObject()): JSONObject =
        JSONObject()
            .put("v", VERSION)
            .put("id", UUID.randomUUID().toString())
            .put("type", type)
            .put("ts", Instant.now().toString())
            .put("body", body)

    fun reply(type: String, replyTo: String, body: JSONObject): JSONObject =
        make(type, body).put("reply_to", replyTo)

    fun encodeJson(obj: JSONObject): ByteArray = encode(TYPE_JSON, obj.toString().toByteArray())

    fun encode(frameType: Int, payload: ByteArray): ByteArray {
        require(payload.size <= MAX_PAYLOAD) { "frame exceeds 1 MiB" }
        val out = ByteArray(5 + payload.size)
        out[0] = (payload.size ushr 24).toByte()
        out[1] = (payload.size ushr 16).toByte()
        out[2] = (payload.size ushr 8).toByte()
        out[3] = payload.size.toByte()
        out[4] = frameType.toByte()
        payload.copyInto(out, 5)
        return out
    }

    /** @return null on a clean EOF between frames (peer closed). */
    fun readFrame(input: InputStream): Pair<Int, ByteArray>? {
        val header = ByteArray(5)
        var read = 0
        while (read < 5) {
            val n = input.read(header, read, 5 - read)
            if (n < 0) {
                if (read == 0) return null
                throw EOFException("truncated frame header")
            }
            read += n
        }
        val length = ((header[0].toInt() and 0xff) shl 24) or
            ((header[1].toInt() and 0xff) shl 16) or
            ((header[2].toInt() and 0xff) shl 8) or
            (header[3].toInt() and 0xff)
        require(length in 0..MAX_PAYLOAD) { "frame length $length exceeds $MAX_PAYLOAD" }
        val type = header[4].toInt()
        require(type == TYPE_JSON || type == TYPE_BLOB) { "unknown frame type $type" }
        val payload = ByteArray(length)
        var offset = 0
        while (offset < length) {
            val n = input.read(payload, offset, length - offset)
            if (n < 0) throw EOFException("truncated frame payload")
            offset += n
        }
        return type to payload
    }

    fun writeFrame(output: OutputStream, frameType: Int, payload: ByteArray) {
        output.write(encode(frameType, payload))
        output.flush()
    }

    fun writeJson(output: OutputStream, obj: JSONObject) =
        writeFrame(output, TYPE_JSON, obj.toString().toByteArray())

    fun blob(header: JSONObject, data: ByteArray): ByteArray {
        val head = header.toString().toByteArray()
        val out = ByteArray(4 + head.size + data.size)
        out[0] = (head.size ushr 24).toByte()
        out[1] = (head.size ushr 16).toByte()
        out[2] = (head.size ushr 8).toByte()
        out[3] = head.size.toByte()
        head.copyInto(out, 4)
        data.copyInto(out, 4 + head.size)
        return out
    }

    fun decodeBlob(payload: ByteArray): Pair<JSONObject, ByteArray> {
        require(payload.size >= 4) { "blob frame too short" }
        val headSize = ((payload[0].toInt() and 0xff) shl 24) or
            ((payload[1].toInt() and 0xff) shl 16) or
            ((payload[2].toInt() and 0xff) shl 8) or
            (payload[3].toInt() and 0xff)
        require(headSize in 1..65536 && 4 + headSize <= payload.size) { "invalid blob header" }
        val header = JSONObject(String(payload, 4, headSize))
        return header to payload.copyOfRange(4 + headSize, payload.size)
    }

    fun b64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)

    fun unb64(value: String): ByteArray = Base64.getDecoder().decode(value)

    fun error(code: String, message: String): JSONObject =
        JSONObject().put("code", code).put("message", message.take(512))
}
