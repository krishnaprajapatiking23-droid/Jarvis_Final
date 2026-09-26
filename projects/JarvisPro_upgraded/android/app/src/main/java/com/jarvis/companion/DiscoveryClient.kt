package com.jarvis.companion

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * Optional local-network discovery (Phase 7).
 *
 * Broadcasts a small UDP probe and collects replies from Jarvis servers.
 * Discovery is never required: manual host/port entry remains available and
 * no subnet is assumed.
 */
object DiscoveryClient {

    const val PORT = 8766
    const val PROBE = "JARVIS_DISCOVER_V1"
    const val TIMEOUT_MS = 2000

    data class Server(
        val name: String,
        val host: String,
        val port: Int,
        val useTls: Boolean
    ) {
        fun toConfig(token: String = ""): ServerConfig =
            ServerConfig(host = host, port = port, token = token, useTls = useTls)
    }

    /** Blocking discovery sweep. Call from a worker thread. */
    fun discover(listenPort: Int = PORT): List<Server> {
        val found = LinkedHashMap<String, Server>()
        val socket = DatagramSocket()
        try {
            socket.broadcast = true
            socket.soTimeout = TIMEOUT_MS
            val payload = PROBE.toByteArray()
            socket.send(
                DatagramPacket(
                    payload,
                    payload.size,
                    InetAddress.getByName("255.255.255.255"),
                    listenPort
                )
            )

            val buffer = ByteArray(2048)
            val deadline = System.currentTimeMillis() + TIMEOUT_MS
            while (System.currentTimeMillis() < deadline) {
                val packet = DatagramPacket(buffer, buffer.size)
                try {
                    socket.receive(packet)
                } catch (timeout: java.net.SocketTimeoutException) {
                    break
                }
                val text = String(packet.data, 0, packet.length)
                val sender = packet.address?.hostAddress ?: ""
                val server = parse(text, sender) ?: continue
                found[server.host + ":" + server.port] = server
            }
        } catch (error: Exception) {
            // Discovery is best-effort; manual configuration still works.
        } finally {
            socket.close()
        }
        return found.values.toList()
    }

    private fun parse(frame: String, sender: String): Server? {
        return try {
            val json = JSONObject(frame)
            if (json.optString("service") != "jarvis") return null
            Server(
                name = json.optString("name", "Jarvis"),
                host = json.optString("host", sender).ifBlank { sender },
                port = json.optInt("port", ServerConfig.DEFAULT_PORT),
                useTls = json.optBoolean("tls", false)
            )
        } catch (error: Exception) {
            null
        }
    }
}
