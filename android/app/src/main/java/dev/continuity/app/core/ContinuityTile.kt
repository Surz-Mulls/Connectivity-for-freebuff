package dev.continuity.app.core

import android.content.Intent
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import dev.continuity.app.MainActivity

/** Quick Settings tile: connection state plus one safe action (open the app). */
class ContinuityTile : TileService() {
    override fun onStartListening() {
        val tile = qsTile ?: return
        val service = ContinuityService.current
        val connected = service != null
        tile.state = if (connected) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = if (connected) "Continuity · on" else "Continuity · off"
        tile.subtitle = if (connected) "Paired session available" else "Tap to open"
        tile.updateTile()
    }

    override fun onClick() {
        val intent = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivityAndCollapse(
            android.app.PendingIntent.getActivity(
                this, 0, intent,
                android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT
            )
        )
    }
}
