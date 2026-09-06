package com.encelerate.fiiodirectremote.ui

import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.encelerate.fiiodirectremote.ui.screens.HomeScreen
import com.encelerate.fiiodirectremote.ui.theme.FiiOK17Theme

class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            FiiOK17Theme {
                val uiState by viewModel.uiState.collectAsState()

                Surface(modifier = Modifier.fillMaxSize()) {
                    HomeScreen(
                        uiState = uiState,
                        onRefresh = { viewModel.refreshStatus(forceRefreshIp = true) },
                        onSetVolume = { vol -> viewModel.setVolume(vol) },
                        onAdjustVolume = { delta -> viewModel.adjustVolume(delta) },
                        onSetInputMode = { modeCode -> viewModel.setInputMode(modeCode) },
                        onToggleNotification = { enabled -> viewModel.toggleMediaNotification(enabled) },
                        onUpdateTimeout = { timeout -> viewModel.updateIdleTimeout(timeout) },
                        onUpdateManualIp = { ip -> viewModel.updateManualIp(ip) },
                        onUpdateStepSize = { step -> viewModel.updateStepSize(step) }
                    )
                }
            }
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        val state = viewModel.uiState.value
        val step = state.settings.stepSize

        when (keyCode) {
            KeyEvent.KEYCODE_VOLUME_UP -> {
                viewModel.adjustVolume(step)
                return true
            }
            KeyEvent.KEYCODE_VOLUME_DOWN -> {
                viewModel.adjustVolume(-step)
                return true
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onResume() {
        super.onResume()
        viewModel.refreshStatus()
    }
}
