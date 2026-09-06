package com.encelerate.fiiodirectremote.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.encelerate.fiiodirectremote.data.*
import com.encelerate.fiiodirectremote.service.K17RemoteService
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class MainUiState(
    val status: K17Status = K17Status(isOnline = false),
    val isConnecting: Boolean = false,
    val resolvedIp: String? = null,
    val settings: UserSettings = UserSettings()
)

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val backend = K17Backend.getInstance(application)
    private val preferencesRepo = UserPreferencesRepository.getInstance(application)

    private val _uiState = MutableStateFlow(MainUiState())
    val uiState: StateFlow<MainUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            combine(
                backend.statusFlow,
                backend.isConnecting,
                backend.resolvedIpFlow,
                preferencesRepo.userSettingsFlow
            ) { status, isConnecting, resolvedIp, settings ->
                MainUiState(
                    status = status,
                    isConnecting = isConnecting,
                    resolvedIp = resolvedIp,
                    settings = settings
                )
            }.collect { combinedState ->
                _uiState.value = combinedState
            }
        }

        // Initial connect / fetch
        refreshStatus()
    }

    fun refreshStatus(forceRefreshIp: Boolean = false) {
        viewModelScope.launch {
            val status = backend.fetchStatus(forceRefreshIp)
            if (status.isOnline && _uiState.value.settings.showMediaNotification) {
                K17RemoteService.start(getApplication())
            }
        }
    }

    fun setVolume(volume: Int) {
        viewModelScope.launch {
            backend.setVolume(volume)
        }
    }

    fun adjustVolume(delta: Int) {
        viewModelScope.launch {
            backend.adjustVolume(delta)
        }
    }

    fun setInputMode(modeCode: String) {
        viewModelScope.launch {
            backend.setInputMode(modeCode)
        }
    }

    fun toggleMediaNotification(enabled: Boolean) {
        viewModelScope.launch {
            preferencesRepo.updateShowMediaNotification(enabled)
            if (enabled) {
                if (_uiState.value.status.isOnline) {
                    K17RemoteService.start(getApplication())
                }
            } else {
                K17RemoteService.stop(getApplication())
            }
        }
    }

    fun updateIdleTimeout(seconds: Int) {
        viewModelScope.launch {
            preferencesRepo.updateIdleTimeoutSec(seconds)
        }
    }

    fun updateManualIp(ip: String) {
        viewModelScope.launch {
            preferencesRepo.updateManualIp(ip)
            backend.invalidateIpCache()
            refreshStatus(forceRefreshIp = true)
        }
    }

    fun updateStepSize(stepSize: Int) {
        viewModelScope.launch {
            preferencesRepo.updateStepSize(stepSize)
        }
    }
}
