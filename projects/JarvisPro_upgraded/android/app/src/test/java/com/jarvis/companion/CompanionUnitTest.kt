package com.jarvis.companion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM unit tests for the pure logic of the companion: configuration
 * validation / URL building and the JSON protocol. No device or emulator is
 * needed, but the Android SDK and Gradle are (ENVIRONMENT TEST REQUIRED in
 * the repair sandbox).
 */
class CompanionUnitTest {

    @Test
    fun emptyHostIsRejected() {
        assertNotNull(ServerConfig().validate())
        assertFalse(ServerConfig().isConfigured)
    }

    @Test
    fun portRangeIsValidated() {
        assertNotNull(ServerConfig(host = "10.1.2.3", port = 0).validate())
        assertNotNull(ServerConfig(host = "10.1.2.3", port = 70000).validate())
        assertNull(ServerConfig(host = "10.1.2.3", port = 8765).validate())
    }

    @Test
    fun urlsFollowTheTlsFlag() {
        val plain = ServerConfig(host = "192.168.0.42", port = 8765)
        assertEquals("ws://192.168.0.42:8765/ws", plain.webSocketUrl)
        assertEquals("http://192.168.0.42:8765", plain.httpUrl)

        val secure = plain.copy(useTls = true)
        assertEquals("wss://192.168.0.42:8765/ws", secure.webSocketUrl)
        assertEquals("https://192.168.0.42:8765", secure.httpUrl)
    }

    @Test
    fun pairingRequiresAToken() {
        assertFalse(ServerConfig(host = "10.1.2.3").isPaired)
        assertTrue(ServerConfig(host = "10.1.2.3", token = "abc").isPaired)
    }

    @Test
    fun commandEnvelopeHasTheRequiredFields() {
        val frame = JarvisProtocol.command("what is the time")
        assertEquals("command", frame.getString("type"))
        assertTrue(frame.getString("id").isNotBlank())
        assertTrue(frame.getString("timestamp").isNotBlank())
        assertEquals(
            "what is the time",
            frame.getJSONObject("payload").getString("text")
        )
    }

    @Test
    fun okResponseIsParsed() {
        val frame = JSONObject()
            .put("id", "1")
            .put("type", "command")
            .put("status", "ok")
            .put("payload", JSONObject().put("reply", "It is noon"))
            .toString()
        val parsed = JarvisProtocol.parse(frame)
        assertTrue(parsed.isOk)
        assertEquals("It is noon", parsed.text())
    }

    @Test
    fun malformedFrameBecomesAnError() {
        val parsed = JarvisProtocol.parse("not json")
        assertFalse(parsed.isOk)
        assertTrue(parsed.error.startsWith("Malformed server frame"))
    }

    @Test
    fun discoveredServerConvertsToConfig() {
        val server = DiscoveryClient.Server("Jarvis", "10.9.8.7", 8765, false)
        val config = server.toConfig("token123")
        assertEquals("10.9.8.7", config.host)
        assertEquals(8765, config.port)
        assertTrue(config.isPaired)
    }
}
