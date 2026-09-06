package com.quirkies.fiiok17.data

import android.content.Context
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.InputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicInteger

class K17Backend private constructor(private val context: Context) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val preferencesRepository = UserPreferencesRepository.getInstance(context)

    private val _statusFlow = MutableStateFlow(K17Status(isOnline = false))
    val statusFlow: StateFlow<K17Status> = _statusFlow.asStateFlow()

    private val _isConnecting = MutableStateFlow(false)
    val isConnecting: StateFlow<Boolean> = _isConnecting.asStateFlow()

    private val _resolvedIpFlow = MutableStateFlow<String?>(null)
    val resolvedIpFlow: StateFlow<String?> = _resolvedIpFlow.asStateFlow()

    private val socketMutex = Mutex()
    private var activeSocket: Socket? = null
    private var socketOutputStream: OutputStream? = null
    private var socketInputStream: InputStream? = null
    private var connectedIp: String? = null
    private var lastUsedTimestamp: Long = 0L

    private var idleDisconnectJob: Job? = null
    private var presenceJob: Job? = null
    private val consecutiveFailures = AtomicInteger(0)

    @Volatile
    private var cachedIp: String? = null

    @Volatile
    private var configuredTimeoutSec: Int = 10

    init {
        // Observe settings changes & initialize last known state
        scope.launch {
            preferencesRepository.userSettingsFlow.collect { settings ->
                configuredTimeoutSec = settings.idleTimeoutSec
                if (settings.manualIp.isNotBlank() && settings.manualIp != cachedIp) {
                    cachedIp = settings.manualIp
                    _resolvedIpFlow.value = cachedIp
                }
                // Seed initial status mode/volume if current status has none
                if (_statusFlow.value.modeCode == null && settings.lastKnownMode.isNotBlank()) {
                    _statusFlow.value = _statusFlow.value.copy(
                        modeCode = settings.lastKnownMode,
                        volume = _statusFlow.value.volume ?: settings.lastKnownVolume
                    )
                }
            }
        }
    }

    suspend fun getOrResolveIp(forceRefresh: Boolean = false): String? = withContext(Dispatchers.IO) {
        if (!forceRefresh && cachedIp != null) {
            return@withContext cachedIp
        }
        val ip = K17Discovery.resolveTargetIp(context, manualIp = cachedIp)
        if (ip != null) {
            cachedIp = ip
            _resolvedIpFlow.value = ip
        }
        return@withContext ip
    }

    fun invalidateIpCache() {
        cachedIp = null
        _resolvedIpFlow.value = null
        closeSocketInternal("Cache invalidated")
    }

    private fun closeSocketInternal(reason: String) {
        try {
            Log.d(TAG, "Closing socket ($reason)")
            activeSocket?.close()
        } catch (e: Exception) {
            Log.w(TAG, "Exception while closing socket: ${e.message}")
        } finally {
            activeSocket = null
            socketOutputStream = null
            socketInputStream = null
            connectedIp = null
        }
    }

    private fun scheduleIdleDisconnect(timeoutSec: Int) {
        idleDisconnectJob?.cancel()
        idleDisconnectJob = scope.launch {
            delay(timeoutSec * 1000L)
            socketMutex.withLock {
                val idleTime = System.currentTimeMillis() - lastUsedTimestamp
                if (idleTime >= timeoutSec * 1000L) {
                    Log.d(TAG, "Idle disconnect timeout ($timeoutSec s) reached. Releasing TCP socket.")
                    closeSocketInternal("Idle timeout")
                }
            }
        }
    }

    private suspend fun ensureSocket(ip: String): Pair<OutputStream, InputStream> {
        val now = System.currentTimeMillis()
        if (activeSocket != null && (connectedIp != ip || activeSocket?.isClosed == true || !activeSocket!!.isConnected)) {
            closeSocketInternal("IP mismatch or socket closed")
        }

        if (activeSocket == null) {
            Log.d(TAG, "Opening new socket connection to $ip:${K17Protocol.DEFAULT_PORT}...")
            val socket = Socket()
            socket.soTimeout = 2500
            socket.tcpNoDelay = true
            socket.connect(InetSocketAddress(ip, K17Protocol.DEFAULT_PORT), 2500)
            activeSocket = socket
            socketOutputStream = socket.getOutputStream()
            socketInputStream = socket.getInputStream()
            connectedIp = ip
            Log.d(TAG, "Socket connected to $ip:${K17Protocol.DEFAULT_PORT}")
        }

        lastUsedTimestamp = now
        return Pair(socketOutputStream!!, socketInputStream!!)
    }

    suspend fun executeCommand(payload: String): Pair<Boolean, String> = withContext(Dispatchers.IO) {
        socketMutex.withLock {
            val ip = getOrResolveIp() ?: run {
                _statusFlow.value = _statusFlow.value.copy(isOnline = false)
                return@withLock Pair(false, "Could not resolve K17 IP")
            }

            for (attempt in 0..1) {
                try {
                    val (outStream, inStream) = ensureSocket(ip)
                    Log.d(TAG, "Transmitting payload: $payload (attempt ${attempt + 1})")
                    outStream.write(payload.toByteArray(Charsets.US_ASCII))
                    outStream.flush()

                    val buffer = ByteArray(2048)
                    val isJsonQuery = payload.startsWith("0501")
                    val responseBuilder = StringBuilder()
                    val startTime = System.currentTimeMillis()

                    while (System.currentTimeMillis() - startTime < 2500) {
                        val bytesRead = inStream.read(buffer)
                        if (bytesRead == -1) {
                            Log.d(TAG, "EOF received from K17")
                            closeSocketInternal("EOF")
                            break
                        }
                        val chunk = String(buffer, 0, bytesRead, Charsets.UTF_8)
                        responseBuilder.append(chunk)

                        if (isJsonQuery && responseBuilder.contains("}")) {
                            break
                        }
                        if (!isJsonQuery && responseBuilder.length >= 12) {
                            break
                        }
                    }

                    val response = responseBuilder.toString()
                    Log.d(TAG, "Received response: '$response' (length ${response.length})")
                    lastUsedTimestamp = System.currentTimeMillis()
                    consecutiveFailures.set(0)

                    // Reschedule idle disconnect
                    val currentTimeout = configuredTimeoutSec
                    scheduleIdleDisconnect(currentTimeout)

                    return@withLock Pair(true, response)
                } catch (e: Exception) {
                    Log.w(TAG, "Socket exception during command '$payload' (attempt ${attempt + 1})", e)
                    closeSocketInternal("Exception: ${e.message}")
                    if (attempt == 0) {
                        delay(200)
                        continue
                    }
                    val fails = consecutiveFailures.incrementAndGet()
                    if (fails >= 2) {
                        _statusFlow.value = _statusFlow.value.copy(isOnline = false)
                    }
                    return@withLock Pair(false, e.message ?: "Socket transmission failed")
                }
            }

            return@withLock Pair(false, "Command failed after retry")
        }
    }

    suspend fun fetchStatus(forceRefreshIp: Boolean = false): K17Status = withContext(Dispatchers.IO) {
        _isConnecting.value = true
        try {
            if (forceRefreshIp) {
                getOrResolveIp(forceRefresh = true)
            }

            val (success, response) = executeCommand(K17Protocol.CMD_STATUS_POLL)
            val status = if (success) {
                val parsed = K17Protocol.parseStatusResponse(response)
                var resolvedMode = parsed.modeCode

                // If status poll did not include an input mode frame, query active mode explicitly
                if (resolvedMode == null && parsed.isOnline) {
                    val (modeQuerySuccess, modeResponse) = executeCommand(K17Protocol.CMD_QUERY_MODE)
                    if (modeQuerySuccess) {
                        resolvedMode = K17Protocol.parseModeQueryResponse(modeResponse)
                    }
                }

                // Fallback to currently known mode code if still null
                val effectiveModeCode = resolvedMode ?: _statusFlow.value.modeCode
                val finalStatus = parsed.copy(modeCode = effectiveModeCode)
                if (finalStatus.isOnline) {
                    // Update last known preferences
                    scope.launch {
                        preferencesRepository.updateLastKnownState(finalStatus.volume, finalStatus.modeCode)
                    }
                }
                finalStatus
            } else {
                K17Status(isOnline = false)
            }

            _statusFlow.value = status
            return@withContext status
        } finally {
            _isConnecting.value = false
        }
    }

    suspend fun setVolume(volume: Int): Boolean {
        val clamped = volume.coerceIn(0, 100)
        // Optimistic UI update
        _statusFlow.value = _statusFlow.value.copy(volume = clamped)

        val cmd = K17Protocol.buildVolumeCommand(clamped)
        val (success, _) = executeCommand(cmd)
        if (success) {
            scope.launch {
                preferencesRepository.updateLastKnownState(clamped, null)
            }
        }
        return success
    }

    suspend fun adjustVolume(delta: Int): Boolean {
        val current = _statusFlow.value.volume ?: 50
        val target = (current + delta).coerceIn(0, 100)
        return setVolume(target)
    }

    suspend fun setInputMode(modeCode: String): Boolean {
        // Optimistic UI update
        _statusFlow.value = _statusFlow.value.copy(modeCode = modeCode)

        val cmd = K17Protocol.buildInputModeCommand(modeCode)
        val (success, _) = executeCommand(cmd)
        if (success) {
            scope.launch {
                preferencesRepository.updateLastKnownState(null, modeCode)
            }
        }
        return success
    }

    suspend fun cycleInputMode(): Boolean {
        val currentCode = _statusFlow.value.modeCode ?: "0001"
        val modes = K17Protocol.INPUT_MODES
        val currentIndex = modes.indexOfFirst { it.code.equals(currentCode, ignoreCase = true) }
        val nextIndex = if (currentIndex == -1 || currentIndex >= modes.size - 1) 0 else currentIndex + 1
        val nextMode = modes[nextIndex]
        return setInputMode(nextMode.code)
    }

    fun startPresenceMonitoring() {
        if (presenceJob?.isActive == true) return
        presenceJob = scope.launch {
            while (isActive) {
                delay(20_000L)
                if (_statusFlow.value.isOnline) {
                    fetchStatus()
                }
            }
        }
    }

    fun stopPresenceMonitoring() {
        presenceJob?.cancel()
        presenceJob = null
    }

    companion object {
        private const val TAG = "K17Backend"

        @Volatile
        private var INSTANCE: K17Backend? = null

        fun getInstance(context: Context): K17Backend {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: K17Backend(context.applicationContext).also { INSTANCE = it }
            }
        }
    }
}
