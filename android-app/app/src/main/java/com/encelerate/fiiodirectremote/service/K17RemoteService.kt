package com.encelerate.fiiodirectremote.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build
import android.os.IBinder
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import android.util.Log
import androidx.core.app.NotificationCompat
import com.encelerate.fiiodirectremote.R
import com.encelerate.fiiodirectremote.data.K17Backend
import com.encelerate.fiiodirectremote.data.K17Status
import com.encelerate.fiiodirectremote.data.UserPreferencesRepository
import com.encelerate.fiiodirectremote.ui.MainActivity
import kotlinx.coroutines.*

class K17RemoteService : Service() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var backend: K17Backend
    private lateinit var preferencesRepo: UserPreferencesRepository
    private var mediaSession: MediaSessionCompat? = null
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "onCreate")
        backend = K17Backend.getInstance(this)
        preferencesRepo = UserPreferencesRepository.getInstance(this)

        createNotificationChannel()
        setupMediaSession()
        registerNetworkCallback()
        observeStatus()
        backend.startPresenceMonitoring()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        Log.d(TAG, "onStartCommand action: $action")

        when (action) {
            ACTION_STOP_SERVICE -> {
                stopForegroundService()
                return START_NOT_STICKY
            }
            ACTION_VOL_UP -> {
                serviceScope.launch { backend.adjustVolume(2) }
            }
            ACTION_VOL_DOWN -> {
                serviceScope.launch { backend.adjustVolume(-2) }
            }
            ACTION_CYCLE_MODE -> {
                serviceScope.launch { backend.cycleInputMode() }
            }
            else -> {
                val notification = buildNotification(backend.statusFlow.value)
                startForeground(NOTIFICATION_ID, notification)
                serviceScope.launch {
                    backend.fetchStatus()
                }
            }
        }

        return START_STICKY
    }

    private fun setupMediaSession() {
        mediaSession = MediaSessionCompat(this, "FiiODirectRemote").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onSeekTo(pos: Long) {
                    // Position in ms (0 to 100_000 ms -> 0 to 100 volume)
                    val vol = (pos / 1000L).toInt().coerceIn(0, 100)
                    Log.d(TAG, "onSeekTo pos: $pos ms -> volume $vol")
                    serviceScope.launch {
                        backend.setVolume(vol)
                    }
                }

                override fun onSkipToNext() {
                    serviceScope.launch { backend.cycleInputMode() }
                }

                override fun onSkipToPrevious() {
                    serviceScope.launch { backend.adjustVolume(-5) }
                }

                override fun onFastForward() {
                    serviceScope.launch { backend.adjustVolume(5) }
                }

                override fun onStop() {
                    stopForegroundService()
                }
            })
            isActive = true
        }
    }

    private fun observeStatus() {
        serviceScope.launch {
            backend.statusFlow.collect { status ->
                updatePlaybackState(status)
                val notification = buildNotification(status)
                val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                notificationManager.notify(NOTIFICATION_ID, notification)
            }
        }

        serviceScope.launch {
            preferencesRepo.userSettingsFlow.collect { settings ->
                if (!settings.showMediaNotification) {
                    Log.d(TAG, "Media notification disabled in settings, stopping foreground service")
                    stopForegroundService()
                }
            }
        }
    }

    private fun updatePlaybackState(status: K17Status) {
        val session = mediaSession ?: return
        val currentVol = status.volume ?: 50
        val positionMs = currentVol * 1000L

        val metadata = MediaMetadataCompat.Builder()
            .putString(MediaMetadataCompat.METADATA_KEY_TITLE, "FiiO Volume: $currentVol%")
            .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, "Input: ${status.inputMode?.name ?: "Unknown"}")
            .putString(MediaMetadataCompat.METADATA_KEY_ALBUM, "Network Remote Control")
            .putLong(MediaMetadataCompat.METADATA_KEY_DURATION, 100_000L) // 100 seconds = 100%
            .build()
        session.setMetadata(metadata)

        val playbackState = PlaybackStateCompat.Builder()
            .setState(
                if (status.isOnline) PlaybackStateCompat.STATE_PLAYING else PlaybackStateCompat.STATE_PAUSED,
                positionMs,
                0f // playback speed 0 so seekbar stays fixed until scrubbed
            )
            .setActions(
                PlaybackStateCompat.ACTION_SEEK_TO or
                PlaybackStateCompat.ACTION_SKIP_TO_NEXT or
                PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS or
                PlaybackStateCompat.ACTION_STOP
            )
            .build()
        session.setPlaybackState(playbackState)
    }

    private fun buildNotification(status: K17Status): Notification {
        val currentVol = status.volume?.let { "$it%" } ?: "--"
        val currentMode = status.inputMode?.name ?: "Unknown Mode"
        val isOnline = status.isOnline

        val openAppIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openAppPendingIntent = PendingIntent.getActivity(
            this, 0, openAppIntent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val stopIntent = Intent(this, K17RemoteService::class.java).apply {
            action = ACTION_STOP_SERVICE
        }
        val stopPendingIntent = PendingIntent.getService(
            this, 1, stopIntent, PendingIntent.FLAG_IMMUTABLE
        )

        val volDownIntent = Intent(this, K17RemoteService::class.java).apply { action = ACTION_VOL_DOWN }
        val volDownPendingIntent = PendingIntent.getService(this, 2, volDownIntent, PendingIntent.FLAG_IMMUTABLE)

        val volUpIntent = Intent(this, K17RemoteService::class.java).apply { action = ACTION_VOL_UP }
        val volUpPendingIntent = PendingIntent.getService(this, 3, volUpIntent, PendingIntent.FLAG_IMMUTABLE)

        val cycleModeIntent = Intent(this, K17RemoteService::class.java).apply { action = ACTION_CYCLE_MODE }
        val cycleModePendingIntent = PendingIntent.getService(this, 4, cycleModeIntent, PendingIntent.FLAG_IMMUTABLE)

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_k17_notification)
            .setContentTitle("FiiO K17 - Vol: $currentVol")
            .setContentText(if (isOnline) "Input: $currentMode" else "Offline / Disconnected")
            .setContentIntent(openAppPendingIntent)
            .setOngoing(isOnline)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(R.drawable.ic_vol_down, "-2", volDownPendingIntent)
            .addAction(R.drawable.ic_input_cycle, currentMode, cycleModePendingIntent)
            .addAction(R.drawable.ic_vol_up, "+2", volUpPendingIntent)
            .addAction(R.drawable.ic_close, "Stop", stopPendingIntent)

        mediaSession?.let { session ->
            builder.setStyle(
                androidx.media.app.NotificationCompat.MediaStyle()
                    .setMediaSession(session.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2)
            )
        }

        return builder.build()
    }

    private fun registerNetworkCallback() {
        connectivityManager = getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .addTransportType(NetworkCapabilities.TRANSPORT_ETHERNET)
            .build()

        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onLost(network: Network) {
                Log.d(TAG, "Wi-Fi connection lost, stopping service")
                stopForegroundService()
            }
        }
        connectivityManager?.registerNetworkCallback(request, networkCallback!!)
    }

    private fun stopForegroundService() {
        backend.stopPresenceMonitoring()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "FiiO Direct Remote",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Volume seekbar and controls for FiiO DAC"
                setShowBadge(false)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "onDestroy")
        networkCallback?.let { connectivityManager?.unregisterNetworkCallback(it) }
        mediaSession?.release()
        mediaSession = null
        serviceScope.cancel()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val TAG = "K17RemoteService"
        const val CHANNEL_ID = "k17_remote_channel"
        const val NOTIFICATION_ID = 1017

        const val ACTION_STOP_SERVICE = "com.encelerate.fiiodirectremote.ACTION_STOP"
        const val ACTION_VOL_UP = "com.encelerate.fiiodirectremote.ACTION_VOL_UP"
        const val ACTION_VOL_DOWN = "com.encelerate.fiiodirectremote.ACTION_VOL_DOWN"
        const val ACTION_CYCLE_MODE = "com.encelerate.fiiodirectremote.ACTION_CYCLE_MODE"

        fun start(context: Context) {
            val intent = Intent(context, K17RemoteService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            val intent = Intent(context, K17RemoteService::class.java).apply {
                action = ACTION_STOP_SERVICE
            }
            context.startService(intent)
        }
    }
}
