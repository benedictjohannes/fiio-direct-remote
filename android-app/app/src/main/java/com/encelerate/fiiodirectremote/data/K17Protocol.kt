package com.encelerate.fiiodirectremote.data

import org.json.JSONObject
import java.util.Locale
import java.util.regex.Pattern

data class InputMode(
    val code: String,
    val name: String,
    val shortName: String
)

data class K17Status(
    val isOnline: Boolean,
    val volume: Int? = null,
    val modeCode: String? = null,
    val maxVolume: Int = 100,
    val rawJson: String? = null
) {
    val inputMode: InputMode?
        get() = K17Protocol.findInputMode(modeCode)
}

object K17Protocol {
    const val DEFAULT_PORT = 12100
    const val MDNS_HOSTNAME = "ingenic.local"
    const val MAC_PREFIX = "40:d9:5a"

    // Multicast UDP Discovery
    const val MULTICAST_GROUP = "224.0.0.255"
    const val MULTICAST_PORT = 12101
    const val MULTICAST_PAYLOAD = "K17"

    // Protocol Opcodes & Prefixes
    const val CMD_HANDSHAKE = "0599000c0000"
    const val CMD_STATUS_POLL = "05010008"
    const val CMD_QUERY_MODE = "0607000c0000"
    const val PREFIX_SET_VOLUME = "0502000c"
    const val PREFIX_SET_MODE = "0657000c"

    val INPUT_MODES = listOf(
        InputMode("0001", "USB Audio", "USB"),
        InputMode("0002", "Optical In", "OPT"),
        InputMode("0003", "Coaxial In", "COAX"),
        InputMode("0004", "Line In", "LINE"),
        InputMode("0005", "Balanced / XLR", "BAL"),
        InputMode("0006", "Bluetooth", "BT"),
        InputMode("0007", "Streaming", "STREAM")
    )

    fun findInputMode(code: String?): InputMode? {
        if (code == null) return null
        return INPUT_MODES.find { it.code.equals(code, ignoreCase = true) }
    }

    fun buildVolumeCommand(volume: Int): String {
        val clamped = volume.coerceIn(0, 100)
        val hex = String.format(Locale.US, "%04X", clamped)
        return "$PREFIX_SET_VOLUME$hex"
    }

    fun buildInputModeCommand(modeCode: String): String {
        return "$PREFIX_SET_MODE$modeCode"
    }

    private val JSON_PATTERN = Pattern.compile("(\\{.*\\})", Pattern.DOTALL)
    private val MODE_PREFIX_PATTERN = Pattern.compile("(?i)a6(?:07000c|0a000c|..000c)([0-9a-f]{4})")

    fun parseModeQueryResponse(rawResponse: String): String? {
        val matcher = MODE_PREFIX_PATTERN.matcher(rawResponse)
        if (matcher.find()) {
            val code = matcher.group(1)?.uppercase(Locale.US)
            if (findInputMode(code) != null) {
                return code
            }
        }
        return null
    }

    fun parseStatusResponse(rawResponse: String): K17Status {
        val matcher = JSON_PATTERN.matcher(rawResponse)
        if (!matcher.find()) {
            return K17Status(isOnline = false)
        }

        return try {
            val jsonStr = matcher.group(1) ?: return K17Status(isOnline = false)
            val json = JSONObject(jsonStr)

            val volume = if (json.has("currentVolume")) {
                json.optInt("currentVolume", -1).takeIf { it in 0..100 }
            } else null

            val maxVol = json.optInt("maxVolume", 100)

            // 1. Try to extract mode code from binary hex prefix (e.g. a607000C0001 or a60a000C000C)
            val modeMatcher = MODE_PREFIX_PATTERN.matcher(rawResponse)
            val extractedCode = if (modeMatcher.find()) {
                modeMatcher.group(1)?.uppercase(Locale.US)
            } else {
                null
            }

            // If extractedCode matches a known input mode (0001..0007), use it
            val modeCode = if (findInputMode(extractedCode) != null) {
                extractedCode
            } else {
                null
            }

            K17Status(
                isOnline = true,
                volume = volume,
                modeCode = modeCode,
                maxVolume = maxVol,
                rawJson = jsonStr
            )
        } catch (e: Exception) {
            K17Status(isOnline = false)
        }
    }
}
