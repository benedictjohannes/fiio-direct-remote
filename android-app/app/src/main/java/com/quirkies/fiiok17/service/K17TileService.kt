package com.quirkies.fiiok17.service

import android.graphics.drawable.Icon
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import androidx.annotation.RequiresApi
import com.quirkies.fiiok17.R
import com.quirkies.fiiok17.data.K17Backend
import kotlinx.coroutines.*

@RequiresApi(Build.VERSION_CODES.N)
class K17TileService : TileService() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var backend: K17Backend

    override fun onCreate() {
        super.onCreate()
        backend = K17Backend.getInstance(this)
    }

    override fun onStartListening() {
        super.onStartListening()
        updateTileState()
        serviceScope.launch {
            backend.statusFlow.collect {
                updateTileState()
            }
        }
    }

    override fun onStopListening() {
        super.onStopListening()
        serviceScope.coroutineContext.cancelChildren()
    }

    override fun onClick() {
        super.onClick()
        val tile = qsTile ?: return
        val isCurrentlyActive = tile.state == Tile.STATE_ACTIVE

        serviceScope.launch {
            if (isCurrentlyActive) {
                // If active, cycle input or stop
                backend.cycleInputMode()
            } else {
                // Connect
                val status = backend.fetchStatus()
                if (status.isOnline) {
                    K17RemoteService.start(applicationContext)
                }
            }
            updateTileState()
        }
    }

    private fun updateTileState() {
        val tile = qsTile ?: return
        val status = backend.statusFlow.value

        if (status.isOnline) {
            tile.state = Tile.STATE_ACTIVE
            tile.label = "K17: ${status.volume ?: "--"}%"
            tile.subtitle = status.inputMode?.shortName ?: "Connected"
            tile.icon = Icon.createWithResource(this, R.drawable.ic_k17_notification)
        } else {
            tile.state = Tile.STATE_INACTIVE
            tile.label = "FiiO K17"
            tile.subtitle = "Disconnected"
            tile.icon = Icon.createWithResource(this, R.drawable.ic_k17_notification)
        }
        tile.updateTile()
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceScope.cancel()
    }
}
