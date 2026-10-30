package dev.continuity.app

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.continuity.app.core.AppState
import dev.continuity.app.core.ContinuityService
import dev.continuity.app.core.NotificationRelay
import dev.continuity.app.core.Store
import dev.continuity.app.ui.Theme
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    private var sharedUri: Uri? = null
    private var handoffUri: Uri? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
        val store = (application as ContinuityApp).store
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Theme.accent,
                    onPrimary = Theme.accentOn,
                    background = Theme.base,
                    onBackground = Theme.text,
                    surface = Theme.surface0,
                    onSurface = Theme.text,
                    surfaceVariant = Theme.surface1,
                    onSurfaceVariant = Theme.subtext,
                    error = Theme.error
                )
            ) {
                Surface(color = MaterialTheme.colorScheme.background) {
                    ContinuityScreen(store)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent == null) return
        when (intent.action) {
            Intent.ACTION_SEND -> sharedUri = intent.getParcelableExtra(Intent.EXTRA_STREAM)
            Intent.ACTION_VIEW -> handoffUri = intent.data
        }
    }

    fun startService(action: String? = null, host: String = "", port: Int = 0,
                     fingerprint: String? = null) {
        val intent = Intent(this, ContinuityService::class.java)
        if (action != null) intent.action = action
        if (host.isNotEmpty()) {
            intent.putExtra("host", host)
            intent.putExtra("port", port)
            intent.putExtra("fingerprint", fingerprint)
        }
        startForegroundService(intent)
    }
}

@Composable
fun ContinuityScreen(store: Store) {
    val context = LocalContext.current
    val activity = context as? MainActivity
    val status by AppState.status.collectAsStateWithLifecycle()
    val pairing by AppState.pairing.collectAsStateWithLifecycle()
    val log by AppState.log.collectAsStateWithLifecycle()
    var tab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Connection", "Share", "Privacy", "Diagnostics")

    Scaffold(
        containerColor = Theme.base,
        topBar = {
            Column {
                Text(
                    "Continuity",
                    color = Theme.text,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(start = 20.dp, top = 20.dp, bottom = 4.dp)
                )
                Text(
                    "Local-only pairing · no cloud account · no telemetry",
                    color = Theme.subtext,
                    modifier = Modifier.padding(start = 20.dp, bottom = 12.dp)
                )
                TabRow(selectedTabIndex = tab, containerColor = Theme.mantle) {
                    tabs.forEachIndexed { index, title ->
                        Tab(
                            selected = tab == index,
                            onClick = { tab = index },
                            text = { Text(title, color = if (tab == index) Theme.accent else Theme.subtext) }
                        )
                    }
                }
            }
        }
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            when (tab) {
                0 -> ConnectionTab(status, pairing, store) { action, host, port, fingerprint ->
                    activity?.startService(action, host, port, fingerprint)
                }
                1 -> ShareTab(status) { activity?.startService(ContinuityService.ACTION_PUSH_CLIPBOARD) }
                2 -> PrivacyTab(store)
                else -> DiagnosticsTab(status, log)
            }
        }
    }
}

@Composable
private fun ConnectionTab(status: JSONObject, pairing: JSONObject?, store: Store,
                          onStart: (String?, String, Int, String?) -> Unit) {
    var host by remember { mutableStateOf(store.lastDesktop?.substringBefore(":") ?: "") }
    var port by remember {
        mutableStateOf(store.lastDesktop?.substringAfter(":", "47820") ?: "47820")
    }
    var fingerprint by remember { mutableStateOf(store.expectedFingerprint() ?: "") }
    val device = status.optJSONObject("device")
    val desktop = status.optJSONObject("desktop")

    InfoCard("This phone") {
        Text(device?.optString("name", "Continuity") ?: "Continuity", color = Theme.text)
        Text("fingerprint", color = Theme.subtext)
        Text(
            device?.optString("fingerprint", "").orEmpty(),
            color = Theme.subtext,
            style = MaterialTheme.typography.bodySmall
        )
        Text(
            if (status.optBoolean("running")) "Listening on port ${status.optInt("port")}"
            else "Service not running",
            color = if (status.optBoolean("running")) Theme.ok else Theme.warn
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { onStart(null, "", 0, null) }) { Text("Start service") }
            Button(onClick = { onStart(ContinuityService.ACTION_STOP, "", 0, null) }) { Text("Stop") }
        }
    }

    InfoCard("Connect to your computer") {
        OutlinedTextField(value = host, onValueChange = { host = it },
            label = { Text("Host / IP") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = port, onValueChange = { port = it.filter(Char::isDigit) },
            label = { Text("Port") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = fingerprint, onValueChange = { fingerprint = it },
            label = { Text("Pinned fingerprint (optional but recommended)") },
            modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            onStart(ContinuityService.ACTION_CONNECT, host, port.toIntOrNull() ?: 47820,
                fingerprint.ifBlank { null })
        }) { Text("Connect") }
        Text(
            "The desktop shows a QR/deep link and a short code. Both devices must show the same "
                + "6 digits and 4 symbols before either side trusts the other.",
            color = Theme.subtext,
            style = MaterialTheme.typography.bodySmall
        )
    }

    if (pairing != null) {
        InfoCard("Confirm pairing") {
            val sas = pairing.optJSONObject("sas")
            Text(pairing.optString("name", "Unknown device"), color = Theme.text)
            Text(
                sas?.optString("digits", "------") ?: "------",
                color = Theme.accent,
                style = MaterialTheme.typography.headlineMedium
            )
            val emoji = sas?.optJSONArray("emoji")
            Text(
                (0 until (emoji?.length() ?: 0)).joinToString(" ") {
                    emoji?.optString(it) ?: ""
                },
                style = MaterialTheme.typography.headlineMedium
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { ContinuityService.current?.answerPairing(true) }) {
                    Text("They match")
                }
                Button(onClick = { ContinuityService.current?.answerPairing(false) }) {
                    Text("Reject")
                }
            }
        }
    }

    InfoCard("Session") {
        Text(
            desktop?.let { "Connected to ${it.optString("name")} (${it.optString("fingerprint").take(16)}…)" }
                ?: "No desktop connected",
            color = if (desktop != null) Theme.ok else Theme.subtext
        )
        Text("${status.optInt("sessions")} session(s)", color = Theme.subtext)
    }
}

@Composable
private fun ShareTab(status: JSONObject, onPushClipboard: () -> Unit) {
    val context = LocalContext.current
    InfoCard("Send from this phone") {
        Text(
            "Use the Android share sheet with any file — Continuity appears as a share target. "
                + "Clipboard reads only ever happen when you press this button (Android 15 blocks "
                + "background clipboard access).",
            color = Theme.subtext
        )
        Button(onClick = onPushClipboard) { Text("Push clipboard to desktop") }
        Button(onClick = {
            context.startActivity(
                Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }) { Text("Notification access settings") }
    }
    InfoCard("Receiving") {
        Text(
            "Files arrive in this app's Downloads/Continuity folder after SHA-256 verification. "
                + "Links from the desktop always ask before opening.",
            color = Theme.subtext
        )
    }
}

@Composable
private fun PrivacyTab(store: Store) {
    var clipboard by remember { mutableStateOf(store.clipboardEnabled) }
    var notifications by remember { mutableStateOf(store.notificationsEnabled) }
    var sensitive by remember { mutableStateOf(store.notificationsIncludeSensitive) }
    var privacy by remember { mutableStateOf(store.privacyMode) }

    InfoCard("Sharing") {
        SwitchRow("Clipboard sync", clipboard) {
            clipboard = it; store.clipboardEnabled = it
        }
        SwitchRow("Mirror notifications", notifications) {
            notifications = it; store.notificationsEnabled = it
        }
        SwitchRow("Include sensitive notifications", sensitive) {
            sensitive = it; store.notificationsIncludeSensitive = it
        }
        SwitchRow("Privacy mode (pause everything)", privacy) {
            privacy = it; store.privacyMode = it
        }
        Text(
            "Android 15 redacts sensitive notifications unless you explicitly grant the "
                + "RECEIVE_SENSITIVE_NOTIFICATIONS app-op. Continuity never runs that command for "
                + "you; it is an opt-in you apply yourself.",
            color = Theme.subtext,
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
private fun DiagnosticsTab(status: JSONObject, log: List<String>) {
    InfoCard("Device") {
        Text("Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})", color = Theme.text)
        Text("${Build.MANUFACTURER} ${Build.MODEL}", color = Theme.subtext)
    }
    InfoCard("Capabilities") {
        Text("service running: ${status.optBoolean("running")}", color = Theme.subtext)
        Text("sessions: ${status.optInt("sessions")}", color = Theme.subtext)
        Text(
            "notification relay: ${if (NotificationRelay.active != null) "connected" else "not connected"}",
            color = Theme.subtext
        )
    }
    InfoCard("Log") {
        log.takeLast(20).forEach { Text("• $it", color = Theme.subtext) }
    }
}

@Composable
private fun InfoCard(title: String, content: @Composable () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Theme.surface0),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, color = Theme.text, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label, color = Theme.text)
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
