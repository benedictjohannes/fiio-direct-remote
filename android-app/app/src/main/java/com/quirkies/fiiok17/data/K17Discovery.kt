package com.quirkies.fiiok17.data

import android.content.Context
import android.net.nsd.NsdManager
import android.net.wifi.WifiManager
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.net.DatagramPacket
import java.net.InetAddress
import java.net.MulticastSocket

object K17Discovery {
    private const val TAG = "K17Discovery"

    suspend fun resolveTargetIp(
        context: Context,
        manualIp: String? = null
    ): String? = withContext(Dispatchers.IO) {
        // 1. Check if user configured a valid manual IP override
        if (!manualIp.isNullOrBlank()) {
            val trimmed = manualIp.trim()
            if (isValidIp(trimmed)) {
                Log.d(TAG, "Using configured manual IP: $trimmed")
                return@withContext trimmed
            }
        }

        // 2. Primary: Listen for UDP multicast heartbeat on 224.0.0.255:12101
        try {
            val multicastResolved = discoverViaMulticast(context)
            if (multicastResolved != null && isValidIp(multicastResolved)) {
                Log.d(TAG, "Resolved K17 via UDP Multicast heartbeat -> $multicastResolved")
                return@withContext multicastResolved
            }
        } catch (e: Exception) {
            Log.w(TAG, "UDP Multicast discovery error: ${e.message}")
        }

        // 3. Fallback: Try standard DNS / mDNS resolution for ingenic.local
        try {
            val addr = InetAddress.getByName(K17Protocol.MDNS_HOSTNAME)
            val resolved = addr.hostAddress
            if (resolved != null && isValidIp(resolved)) {
                Log.d(TAG, "Resolved ${K17Protocol.MDNS_HOSTNAME} -> $resolved via standard DNS/mDNS")
                return@withContext resolved
            }
        } catch (e: Exception) {
            Log.w(TAG, "Standard getByName for ${K17Protocol.MDNS_HOSTNAME} failed: ${e.message}")
        }

        // 4. Fallback: Query NsdManager if available
        try {
            val nsdResolved = resolveViaNsd(context)
            if (nsdResolved != null) {
                Log.d(TAG, "Resolved via NsdManager -> $nsdResolved")
                return@withContext nsdResolved
            }
        } catch (e: Exception) {
            Log.w(TAG, "NsdManager resolution failed: ${e.message}")
        }

        Log.e(TAG, "Could not resolve K17 IP address")
        null
    }

    private fun isValidIp(ip: String): Boolean {
        val parts = ip.split(".")
        if (parts.size != 4) return false
        return parts.all { part ->
            part.toIntOrNull()?.let { it in 0..255 } ?: false
        }
    }

    private suspend fun discoverViaMulticast(
        context: Context,
        timeoutMs: Long = 2500L
    ): String? = withContext(Dispatchers.IO) {
        val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        val multicastLock = wifiManager?.createMulticastLock("k17_multicast_lock")?.apply {
            setReferenceCounted(true)
            acquire()
        }

        var socket: MulticastSocket? = null
        try {
            socket = MulticastSocket(K17Protocol.MULTICAST_PORT).apply {
                soTimeout = timeoutMs.toInt().coerceAtLeast(1000)
                reuseAddress = true
            }

            val group = InetAddress.getByName(K17Protocol.MULTICAST_GROUP)
            socket.joinGroup(group)

            val buffer = ByteArray(256)
            val packet = DatagramPacket(buffer, buffer.size)

            val startTime = System.currentTimeMillis()
            while (System.currentTimeMillis() - startTime < timeoutMs) {
                try {
                    socket.receive(packet)
                    val message = String(packet.data, packet.offset, packet.length, Charsets.US_ASCII).trim()
                    if (message.contains(K17Protocol.MULTICAST_PAYLOAD)) {
                        val senderIp = packet.address.hostAddress
                        Log.d(TAG, "Received K17 multicast heartbeat from $senderIp: '$message'")
                        return@withContext senderIp
                    }
                } catch (e: java.net.SocketTimeoutException) {
                    break
                }
            }
            null
        } catch (e: Exception) {
            Log.w(TAG, "Multicast discovery exception: ${e.message}")
            null
        } finally {
            try {
                socket?.close()
            } catch (_: Exception) {}
            try {
                if (multicastLock?.isHeld == true) {
                    multicastLock.release()
                }
            } catch (_: Exception) {}
        }
    }

    private suspend fun resolveViaNsd(context: Context): String? {
        val nsdManager = context.getSystemService(Context.NSD_SERVICE) as? NsdManager ?: return null
        return withTimeoutOrNull(2000L) {
            try {
                val host = InetAddress.getByName(K17Protocol.MDNS_HOSTNAME)
                host.hostAddress
            } catch (e: Exception) {
                null
            }
        }
    }
}
