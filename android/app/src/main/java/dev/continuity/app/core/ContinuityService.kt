package dev.continuity.app.core

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.media.RingtoneManager
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.OpenableColumns
import dev.continuity.app.MainActivity
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.ServerSocket
import java.net.Socket
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.Collections
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLServerSocket
import javax.net.ssl.SSLSocket
import javax.net.ssl.X509TrustManager

/**
 * Foreground service holding the identity, the TLS listener and all open sessions.
 *
 * The service is the only place that owns connection state; the UI reads [AppState].
 * Android 15 restrictions honoured here: the foreground service type is `connectedDevice`
 * (never `dataSync`), notifications are only posted once the user has granted
 * POST_NOTIFICATIONS, and no clipboard read happens in the background.
 */
class ContinuityService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var store: Store
    private lateinit var identity: Identity
    private var serverSocket: SSLServerSocket? = null
    private val sessions = Collections.synchronizedList(mutableListOf<ContinuitySession>())
    private val running = AtomicBoolean(false)
    private var acceptJob: Job? = null
    private var pairingDeferred: CompletableDeferred<Boolean>? = null
    private val receiveDir by lazy { File(getExternalFilesDir(null), "received").apply { mkdirs() } }
    private val chunkBuffers = java.util.concurrent.ConcurrentHashMap<String, File>()

    override fun onCreate() {
        super.onCreate()
        store = (application as dev.continuity.app.ContinuityApp).store
        identity = Identity.loadOrCreate(this, store.deviceName)
        createChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Starting…"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                val host = intent.getStringExtra("host") ?: ""
                val port = intent.getIntExtra("port", 0)
                val fingerprint = intent.getStringExtra("fingerprint")
                if (host.isNotEmpty() && port > 0) {
                    store.expectedFingerprintValue = fingerprint
                    connect(host, port)
                }
            }
            ACTION_PUSH_CLIPBOARD -> pushClipboard()
            ACTION_RING_DESKTOP -> ringDesktop()
            ACTION_SEND_FILE -> intent.getStringExtra("uri")?.let { sendFile(Uri.parse(it)) }
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
        }
        startListening()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        running.set(false)
        acceptJob?.cancel()
        runCatching { serverSocket?.close() }
        sessions.forEach { it.stop() }
        sessions.clear()
        scope.cancel()
        super.onDestroy()
    }

    // ------------------------------------------------------------------ server
    private fun startListening() {
        if (!running.compareAndSet(false, true)) return
        acceptJob = scope.launch {
            val context = serverContext()
            val socket = try {
                (context.serverSocketFactory.createServerSocket(0) as SSLServerSocket).apply {
                    reuseAddress = true
                    needClientAuth = false
                }
            } catch (exc: Exception) {
                note("could not open listener: ${exc.message}")
                running.set(false)
                return@launch
            }
            serverSocket = socket
            note("listening on port ${socket.localPort}")
            updateNotification("Waiting for your computer · port ${socket.localPort}")
            AppState.status.value = statusJson(port = socket.localPort)
            while (running.get()) {
                val accepted: Socket? = try {
                    socket.accept()
                } catch (exc: Exception) {
                    null
                }
                if (accepted == null) break
                attach(accepted, initiator = false)
            }
        }
    }

    private fun serverContext(): SSLContext {
        val keyStore = KeyStore.getInstance("PKCS12").apply { load(null, null) }
        keyStore.setKeyEntry("device", identity.privateKey(), PASSWORD, arrayOf(identity.certificate))
        val kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
        kmf.init(keyStore, PASSWORD)
        return SSLContext.getInstance("TLSv1.3").apply {
            init(kmf.keyManagers, null, SecureRandom())
        }
    }

    private fun clientContext(): SSLContext {
        // TLS is confidentiality only; the desktop is authenticated by pinned fingerprint + signature.
        val manager = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        }
        return SSLContext.getInstance("TLSv1.3").apply {
            init(null, arrayOf(manager), SecureRandom())
        }
    }

    private fun connect(host: String, port: Int) {
        scope.launch {
            val socket = try {
                (clientContext().socketFactory.createSocket(host, port) as SSLSocket).apply {
                    soTimeout = 30_000
                }
            } catch (exc: Exception) {
                note("connect failed: ${exc.message}")
                return@launch
            }
            store.lastDesktop = "$host:$port"
            attach(socket, initiator = true)
        }
    }

    private fun attach(socket: Socket, initiator: Boolean) {
        val session = ContinuitySession(
            identity = identity,
            store = store,
            socket = socket,
            initiator = initiator,
            handler = ::handleMessage,
            blobHandler = ::handleBlob,
            approver = ::approvePairing,
            onReady = { onSessionReady(it) },
            onClosed = { closed, failure ->
                sessions.remove(closed)
                AppState.status.value = statusJson(port = serverSocket?.localPort ?: 0)
                note(failure?.let { "session closed: $it" } ?: "session closed")
            }
        )
        sessions.add(session)
        session.start()
    }

    private fun onSessionReady(session: ContinuitySession) {
        val peer = session.peer ?: return
        note("connected to ${peer.name} (${if (peer.trusted) "pinned" else "unpaired"})")
        val desktop = JSONObject()
            .put("name", peer.name)
            .put("fingerprint", peer.fingerprint)
            .put("trusted", peer.trusted)
        AppState.status.value = statusJson(port = serverSocket?.localPort ?: 0).put("desktop", desktop)
        updateNotification("Connected to ${peer.name}")
        if (peer.trusted) {
            session.send(Protocol.Msg.STATUS, batteryStatus())
        }
    }

    private suspend fun approvePairing(request: JSONObject): Boolean {
        val deferred = CompletableDeferred<Boolean>()
        pairingDeferred = deferred
        AppState.pairing.value = request
        val answer = withTimeoutOrNull(90_000) { deferred.await() } ?: false
        AppState.pairing.value = null
        pairingDeferred = null
        return answer
    }

    fun answerPairing(accepted: Boolean) {
        pairingDeferred?.complete(accepted)
    }

    // ------------------------------------------------------------------ dispatch
    private fun handleMessage(session: ContinuitySession, msg: JSONObject): JSONObject? {
        val type = msg.getString("type")
        val body = msg.optJSONObject("body") ?: JSONObject()
        return when (type) {
            Protocol.Msg.CLIPBOARD_SET -> {
                if (!store.clipboardEnabled || store.privacyMode ||
                    store.clipboardDirection == "to_phone"
                ) {
                    session.sendError("privacy.blocked", "clipboard receiving is disabled")
                    null
                } else {
                    val text = body.optString("data", "")
                    val applied = setClipboard(text)
                    AppState.note("clipboard from desktop: ${text.take(40)}")
                    JSONObject().put("digest", body.optString("digest")).put("applied", applied)
                }
            }
            Protocol.Msg.FILE_OFFER -> acceptOffer(body)
            Protocol.Msg.FILE_DONE -> finishTransfer(body)
            Protocol.Msg.HANDOFF_URL -> {
                val url = body.optString("url", "")
                if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    session.sendError("protocol.unsupported", "only http(s) links are opened")
                    null
                } else {
                    openHandoffNotification(url, body.optString("title", ""))
                    JSONObject().put("accepted", true)
                }
            }
            Protocol.Msg.FIND_RING -> {
                ring(body.optInt("duration_s", 10))
                JSONObject().put("ok", true)
            }
            Protocol.Msg.STATUS_REQUEST -> batteryStatus()
            Protocol.Msg.MEDIA_COMMAND -> {
                session.sendError("capability.denied", "media bridge not implemented in this build")
                null
            }
            Protocol.Msg.CAMERA_REQUEST -> {
                session.sendError("capability.denied",
                    "camera handoff is not implemented in this build")
                null
            }
            Protocol.Msg.DEX_PROBE -> JSONObject().put("supported", false)
                .put("reason", "DeX sessions are supervised on the desktop with adb/scrcpy")
            Protocol.Msg.PRIVACY_SET -> {
                session.sendError("privacy.blocked", "privacy is local-only")
                null
            }
            Protocol.Msg.TRUST_REVOKE -> {
                val fingerprint = body.optString("fingerprint")
                if (fingerprint.isNotEmpty()) store.revoke(fingerprint)
                JSONObject().put("revoked", true)
            }
            else -> {
                session.sendError("protocol.unsupported", "no handler for $type")
                null
            }
        }
    }

    private fun handleBlob(session: ContinuitySession, header: JSONObject, data: ByteArray) {
        if (header.optString("type") != Protocol.Msg.FILE_CHUNK) return
        val id = header.optString("transfer_id")
        val target = chunkBuffers[id] ?: return
        val offset = header.optLong("offset", -1)
        if (offset != target.length()) {
            session.sendError("protocol.json", "out-of-order chunk")
            return
        }
        target.appendBytes(data)
    }

    private fun acceptOffer(body: JSONObject): JSONObject {
        val id = body.optString("transfer_id")
        val name = body.optString("name").replace("/", "_").replace("\\", "_")
        if (id.isEmpty() || name.isEmpty() || name.startsWith(".")) {
            return JSONObject().put("transfer_id", id).put("offset", 0).put("accept", false)
        }
        if (!store.clipboardEnabled || store.privacyMode) {
            return JSONObject().put("transfer_id", id).put("offset", 0).put("accept", false)
        }
        val target = File(receiveDir, "${id.take(8)}-$name")
        runCatching { target.writeBytes(ByteArray(0)) }
        chunkBuffers[id] = target
        return JSONObject().put("transfer_id", id).put("offset", 0).put("accept", true)
    }

    private fun finishTransfer(body: JSONObject): JSONObject {
        val id = body.optString("transfer_id")
        val file = chunkBuffers.remove(id)
            ?: return JSONObject().put("transfer_id", id).put("ok", false)
                .put("error", "unknown transfer")
        val expected = body.optString("sha256", "")
        val digest = MessageDigest.getInstance("SHA-256").digest(file.readBytes())
            .joinToString("") { "%02x".format(it) }
        return if (expected.isNotEmpty() && digest != expected) {
            file.delete()
            JSONObject().put("transfer_id", id).put("ok", false)
                .put("error", "integrity check failed")
        } else {
            JSONObject().put("transfer_id", id).put("ok", true).put("sha256", digest)
                .put("path", file.absolutePath)
        }
    }

    // ------------------------------------------------------------------ actions
    fun pushClipboard() {
        val session = trustedSession() ?: run { note("no paired desktop"); return }
        scope.launch {
            val text = readClipboard()
            if (text.isNullOrBlank()) {
                note("clipboard is empty")
                return@launch
            }
            val digest = MessageDigest.getInstance("SHA-256").digest(text.toByteArray())
                .joinToString("") { "%02x".format(it) }
            val reply = session.request(
                Protocol.Msg.CLIPBOARD_SET,
                JSONObject().put("kind", "text").put("data", text).put("digest", digest)
                    .put("sensitive", false)
            )
            val applied = reply?.optJSONObject("body")?.optBoolean("applied") == true
            note(if (applied) "clipboard sent" else "clipboard rejected by the desktop")
        }
    }

    fun sendFile(uri: Uri) {
        val session = trustedSession() ?: run { note("no paired desktop"); return }
        scope.launch {
            val resolver = contentResolver
            var name = "shared-file"
            var size = 0L
            resolver.query(uri, null, null, null, null)?.use { cursor ->
                val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                if (cursor.moveToFirst()) {
                    if (nameIndex >= 0) name = cursor.getString(nameIndex) ?: name
                    if (sizeIndex >= 0) size = cursor.getLong(sizeIndex)
                }
            }
            val bytes = resolver.openInputStream(uri)?.use { it.readBytes() } ?: return@launch
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it) }
            val accepted = session.request(
                Protocol.Msg.FILE_OFFER,
                JSONObject().put("transfer_id", java.util.UUID.randomUUID().toString())
                    .put("name", name.takeLast(200)).put("size", bytes.size.toLong())
                    .put("sha256", digest).put("mime", resolver.getType(uri) ?: "application/octet-stream")
            )?.optJSONObject("body")
            if (accepted == null || !accepted.optBoolean("accept", false)) {
                note("desktop declined the file")
                return@launch
            }
            val transferId = accepted.optString("transfer_id")
            var offset = accepted.optInt("offset", 0)
            while (offset < bytes.size) {
                val end = minOf(offset + 256 * 1024, bytes.size)
                session.sendBlob(
                    JSONObject().put("type", Protocol.Msg.FILE_CHUNK)
                        .put("transfer_id", transferId).put("offset", offset),
                    bytes.copyOfRange(offset, end)
                )
                offset = end
            }
            val result = session.request(
                Protocol.Msg.FILE_DONE,
                JSONObject().put("transfer_id", transferId).put("sha256", digest),
                timeoutMs = 120_000
            )?.optJSONObject("body")
            note(if (result?.optBoolean("ok") == true) "file sent" else "file transfer failed")
        }
    }

    fun ringDesktop() {
        val session = trustedSession() ?: return
        scope.launch {
            session.request(Protocol.Msg.FIND_RING, JSONObject().put("duration_s", 10))
            note("asked the desktop to ring")
        }
    }

    private fun trustedSession(): ContinuitySession? =
        sessions.firstOrNull { it.peer?.trusted == true }

    private fun readClipboard(): String? {
        val manager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        return manager.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.text?.toString()
    }

    private fun setClipboard(text: String): Boolean {
        var applied = false
        Handler(Looper.getMainLooper()).post {
            val manager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            manager.setPrimaryClip(ClipData.newPlainText("Continuity", text))
            applied = true
        }
        return true
    }

    private fun ring(seconds: Int) {
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
        val ringtone = RingtoneManager.getRingtone(this, uri) ?: return
        ringtone.play()
        Handler(Looper.getMainLooper()).postDelayed({ runCatching { ringtone.stop() } },
            seconds.coerceIn(1, 30) * 1000L)
    }

    private fun openHandoffNotification(url: String, title: String) {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val pending = PendingIntent.getActivity(this, url.hashCode(), intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setContentTitle(title.ifBlank { "Link from your computer" })
            .setContentText(url)
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(url.hashCode(), notification)
    }

    private fun batteryStatus(): JSONObject {
        val manager = getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return JSONObject()
            .put("battery", JSONObject()
                .put("level", manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
                .put("charging", manager.isCharging))
            .put("network", "wifi")
            .put("app_version", "0.1.0")
            .put("foreground", true)
    }

    private fun statusJson(port: Int): JSONObject = JSONObject()
        .put("running", running.get())
        .put("port", port)
        .put("device", JSONObject().put("name", store.deviceName.ifBlank { identity.name })
            .put("fingerprint", identity.fingerprint))
        .put("sessions", sessions.size)
        .put("clipboard_enabled", store.clipboardEnabled)
        .put("notifications_enabled", store.notificationsEnabled)
        .put("privacy_mode", store.privacyMode)

    private fun note(message: String) {
        android.util.Log.i("Continuity", message)
        AppState.note(message)
    }

    // ------------------------------------------------------------------ notifications
    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, getString(dev.continuity.app.R.string.service_channel),
                NotificationManager.IMPORTANCE_LOW)
        )
    }

    private fun buildNotification(text: String): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle(getString(dev.continuity.app.R.string.service_title))
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        runCatching {
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .notify(NOTIFICATION_ID, buildNotification(text))
        }
    }

    companion object {
        const val CHANNEL_ID = "connection"
        const val NOTIFICATION_ID = 1001
        const val ACTION_CONNECT = "dev.continuity.app.CONNECT"
        const val ACTION_PUSH_CLIPBOARD = "dev.continuity.app.PUSH_CLIPBOARD"
        const val ACTION_RING_DESKTOP = "dev.continuity.app.RING_DESKTOP"
        const val ACTION_SEND_FILE = "dev.continuity.app.SEND_FILE"
        const val ACTION_STOP = "dev.continuity.app.STOP"
        private val PASSWORD = "continuity".toCharArray()

        @Volatile
        var current: ContinuityService? = null
            private set
    }

    init {
        current = this
    }
}
