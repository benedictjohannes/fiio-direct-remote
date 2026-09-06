package com.encelerate.fiiodirectremote

import com.encelerate.fiiodirectremote.data.K17Protocol
import org.junit.Assert.*
import org.junit.Test

class K17ProtocolTest {

    @Test
    fun testBuildVolumeCommand() {
        assertEquals("0502000c0000", K17Protocol.buildVolumeCommand(0))
        assertEquals("0502000c0064", K17Protocol.buildVolumeCommand(100))
        assertEquals("0502000c002D", K17Protocol.buildVolumeCommand(45))
        assertEquals("0502000c000A", K17Protocol.buildVolumeCommand(10))

        // Clamping tests
        assertEquals("0502000c0000", K17Protocol.buildVolumeCommand(-5))
        assertEquals("0502000c0064", K17Protocol.buildVolumeCommand(150))
    }

    @Test
    fun testBuildInputModeCommand() {
        assertEquals("0657000c0001", K17Protocol.buildInputModeCommand("0001"))
        assertEquals("0657000c0002", K17Protocol.buildInputModeCommand("0002"))
        assertEquals("0657000c0003", K17Protocol.buildInputModeCommand("0003"))
        assertEquals("0657000c0004", K17Protocol.buildInputModeCommand("0004"))
        assertEquals("0657000c0005", K17Protocol.buildInputModeCommand("0005"))
        assertEquals("0657000c0006", K17Protocol.buildInputModeCommand("0006"))
        assertEquals("0657000c0007", K17Protocol.buildInputModeCommand("0007"))
    }

    @Test
    fun testInputModeLookup() {
        val usbMode = K17Protocol.findInputMode("0001")
        assertNotNull(usbMode)
        assertEquals("USB Audio", usbMode?.name)
        assertEquals("USB", usbMode?.shortName)

        val optMode = K17Protocol.findInputMode("0002")
        assertNotNull(optMode)
        assertEquals("Optical In", optMode?.name)

        val balMode = K17Protocol.findInputMode("0005")
        assertNotNull(balMode)
        assertEquals("Balanced / XLR", balMode?.name)

        assertNull(K17Protocol.findInputMode("9999"))
        assertNull(K17Protocol.findInputMode(null))
    }

    @Test
    fun testParseStatusResponseValid() {
        val raw = "a607000C0002a5010184{\"currentVolume\":65,\"maxVolume\":100,\"usbAudio\":2,\"power\":1}"
        val status = K17Protocol.parseStatusResponse(raw)

        assertTrue(status.isOnline)
        assertEquals(65, status.volume)
        assertEquals("0002", status.modeCode)
        assertEquals("Optical In", status.inputMode?.name)
        assertEquals(100, status.maxVolume)
    }

    @Test
    fun testParseStatusResponseFramedWithGarbage() {
        val raw = "PREFIX_HEADER_12345a607000c0006{\"currentVolume\":42,\"usbAudio\":2}TRAILING_DATA"
        val status = K17Protocol.parseStatusResponse(raw)

        assertTrue(status.isOnline)
        assertEquals(42, status.volume)
        assertEquals("0006", status.modeCode)
        assertEquals("Bluetooth", status.inputMode?.name)
    }

    @Test
    fun testParseStatusResponseWithoutModePrefix() {
        val raw = "a5010184{\"currentVolume\":50,\"maxVolume\":100,\"usbAudio\":2}"
        val status = K17Protocol.parseStatusResponse(raw)

        assertTrue(status.isOnline)
        assertEquals(50, status.volume)
        assertNull(status.modeCode)
    }

    @Test
    fun testParseModeQueryResponse() {
        assertEquals("0001", K17Protocol.parseModeQueryResponse("a607000C0001"))
        assertEquals("0002", K17Protocol.parseModeQueryResponse("a607000c0002"))
        assertEquals("0003", K17Protocol.parseModeQueryResponse("a607000C0003"))
        assertEquals("0006", K17Protocol.parseModeQueryResponse("PREFIX_a607000C0006_SUFFIX"))
        assertNull(K17Protocol.parseModeQueryResponse("a60a000C000C")) // ACK only, not mode code
        assertNull(K17Protocol.parseModeQueryResponse("a607000C9999")) // Unknown mode
        assertNull(K17Protocol.parseModeQueryResponse("INVALID_FRAME"))
    }

    @Test
    fun testProtocolConstants() {
        assertEquals("05010008", K17Protocol.CMD_STATUS_POLL)
        assertEquals("0599000c0000", K17Protocol.CMD_HANDSHAKE)
        assertEquals("0607000c0000", K17Protocol.CMD_QUERY_MODE)
        assertEquals("224.0.0.255", K17Protocol.MULTICAST_GROUP)
        assertEquals(12101, K17Protocol.MULTICAST_PORT)
        assertEquals("K17", K17Protocol.MULTICAST_PAYLOAD)
    }
}
