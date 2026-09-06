package com.quirkies.fiiok17.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "k17_settings")

data class UserSettings(
    val showMediaNotification: Boolean = false,
    val idleTimeoutSec: Int = 10,
    val manualIp: String = "",
    val stepSize: Int = 2,
    val lastKnownVolume: Int = 50,
    val lastKnownMode: String = "0001"
)

class UserPreferencesRepository(private val context: Context) {

    private object PreferencesKeys {
        val SHOW_MEDIA_NOTIFICATION = booleanPreferencesKey("show_media_notification")
        val IDLE_TIMEOUT_SEC = intPreferencesKey("idle_timeout_sec")
        val MANUAL_IP = stringPreferencesKey("manual_ip")
        val STEP_SIZE = intPreferencesKey("step_size")
        val LAST_KNOWN_VOLUME = intPreferencesKey("last_known_volume")
        val LAST_KNOWN_MODE = stringPreferencesKey("last_known_mode")
    }

    val userSettingsFlow: Flow<UserSettings> = context.dataStore.data
        .map { preferences ->
            UserSettings(
                showMediaNotification = preferences[PreferencesKeys.SHOW_MEDIA_NOTIFICATION] ?: false,
                idleTimeoutSec = preferences[PreferencesKeys.IDLE_TIMEOUT_SEC] ?: 10,
                manualIp = preferences[PreferencesKeys.MANUAL_IP] ?: "",
                stepSize = preferences[PreferencesKeys.STEP_SIZE] ?: 2,
                lastKnownVolume = preferences[PreferencesKeys.LAST_KNOWN_VOLUME] ?: 50,
                lastKnownMode = preferences[PreferencesKeys.LAST_KNOWN_MODE] ?: "0001"
            )
        }

    suspend fun updateShowMediaNotification(enabled: Boolean) {
        context.dataStore.edit { preferences ->
            preferences[PreferencesKeys.SHOW_MEDIA_NOTIFICATION] = enabled
        }
    }

    suspend fun updateIdleTimeoutSec(timeoutSec: Int) {
        context.dataStore.edit { preferences ->
            preferences[PreferencesKeys.IDLE_TIMEOUT_SEC] = timeoutSec.coerceIn(3, 60)
        }
    }

    suspend fun updateManualIp(ip: String) {
        context.dataStore.edit { preferences ->
            preferences[PreferencesKeys.MANUAL_IP] = ip.trim()
        }
    }

    suspend fun updateStepSize(stepSize: Int) {
        context.dataStore.edit { preferences ->
            preferences[PreferencesKeys.STEP_SIZE] = stepSize
        }
    }

    suspend fun updateLastKnownState(volume: Int?, mode: String?) {
        context.dataStore.edit { preferences ->
            if (volume != null) {
                preferences[PreferencesKeys.LAST_KNOWN_VOLUME] = volume
            }
            if (!mode.isNullOrBlank()) {
                preferences[PreferencesKeys.LAST_KNOWN_MODE] = mode
            }
        }
    }

    companion object {
        @Volatile
        private var INSTANCE: UserPreferencesRepository? = null

        fun getInstance(context: Context): UserPreferencesRepository {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: UserPreferencesRepository(context.applicationContext).also { INSTANCE = it }
            }
        }
    }
}
