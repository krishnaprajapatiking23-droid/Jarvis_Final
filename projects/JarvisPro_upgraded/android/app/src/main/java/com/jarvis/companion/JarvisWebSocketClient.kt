package com.jarvis.companion

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** UI-facing connection states (Phase 6). */
enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    AUTH_FAILED,
    SERVER_UNAVAILABLE,
    TIMEOUT
}

/**
 * WebSocket client with authentication, heartbeat, bounded reconnect and
 * explicit state reporting. Callbacks arrive off the UI thread; the activity
 * marshals them back with a Handler.
 */
class JarvisWebSocketClient(
    private val config: ServerConfig,
    private val deviceName: String,
    private val onState: (ConnectionState, String) -> Unit,
    private val onMessage: (JarvisProtocol.Response) -> Unit
) {

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .pingInterval(HEARTBEAT_SECONDS, TimeUnit.SECONDS)
        .build()

    private var socket: WebSocket? = null
    private val closedByUser = AtomicBoolean(false)
    private var attempts = 0

    /** Connect and authenticate. Requires a validated, paired config. */
    fun connect() {
        val problem = config.validate()
        if (problem != null) {
            onState(ConnectionState.DISCONNECTED, problem)
            return
        }
        if (!config.isPaired) {
            onState(ConnectionState.AUTH_FAILED, "Pair with the server first")
            return
        }

        closedByUser.set(false)
        onState(ConnectionState.CONNECTING, config.webSocketUrl)

        val request = Request.Builder()
            .url(config.webSocketUrl)
            .header("Authorization", "Bearer " + config.token)
            .build()

        socket = client.newWebSocket(request, object : WebSocketListener() {

            override fun onOpen(webSocket: WebSocket, response: Response) {
                attempts = 0
                webSocket.send(
                    JarvisProtocol.auth(config.token, deviceName).toString()
                )
                onState(
                    ConnectionState.CONNECTED,
                    "Connected to " + config.hostPort
                )
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val parsed = JarvisProtocol.parse(text)
                if (parsed.type == JarvisProtocol.TYPE_PING) {
                    webSocket.send(
                        JarvisProtocol.envelope(
                            JarvisProtocol.TYPE_PONG,
                            JSONObject(),
                            parsed.id
                        ).toString()
                    )
                    return
                }
                if (parsed.type == JarvisProtocol.TYPE_AUTH && !parsed.isOk) {
                    onState(ConnectionState.AUTH_FAILED, parsed.error)
                    closedByUser.set(true)
                    webSocket.close(NORMAL_CLOSURE, "auth failed")
                    return
                }
                onMessage(parsed)
            }

            override fun onClosed(
                webSocket: WebSocket,
                code: Int,
                reason: String
            ) {
                socket = null
                if (closedByUser.get()) {
                    onState(ConnectionState.DISCONNECTED, "Disconnected")
                } else {
                    scheduleReconnect("Connection closed: " + reason)
                }
            }

            override fun onFailure(
                webSocket: WebSocket,
                t: Throwable,
                response: Response?
            ) {
                socket = null
                Log.w(TAG, "websocket failure", t)
                val code = response?.code ?: 0
                when {
                    code == 401 || code == 403 ->
                        onState(
                            ConnectionState.AUTH_FAILED,
                            "Authentication rejected"
                        )
                    t is java.net.SocketTimeoutException ->
                        scheduleReconnect("Timed out", ConnectionState.TIMEOUT)
                    else ->
                        scheduleReconnect(
                            t.message ?: "Server unavailable",
                            ConnectionState.SERVER_UNAVAILABLE
                        )
                }
            }
        })
    }

    /** Send a command; returns false when the socket is not open. */
    fun sendCommand(text: String): Boolean {
        val active = socket ?: return false
        return active.send(JarvisProtocol.command(text).toString())
    }

    /** Explicit user disconnect: no reconnect is attempted. */
    fun disconnect() {
        closedByUser.set(true)
        socket?.close(NORMAL_CLOSURE, "user disconnected")
        socket = null
        onState(ConnectionState.DISCONNECTED, "Disconnected")
    }

    private fun scheduleReconnect(
        reason: String,
        state: ConnectionState = ConnectionState.SERVER_UNAVAILABLE
    ) {
        if (closedByUser.get()) {
            onState(ConnectionState.DISCONNECTED, reason)
            return
        }
        if (attempts >= MAX_RECONNECT_ATTEMPTS) {
            onState(state, reason + " (giving up after " + attempts + " tries)")
            return
        }
        attempts += 1
        val backoff = minOf(
            BASE_BACKOFF_MS * (1L shl (attempts - 1)),
            MAX_BACKOFF_MS
        )
        onState(state, reason + " - retrying in " + (backoff / 1000) + "s")
        val worker = Thread {
            try {
                Thread.sleep(backoff)
            } catch (interrupted: InterruptedException) {
                return@Thread
            }
            if (!closedByUser.get()) {
                connect()
            }
        }
        worker.name = "jarvis-reconnect"
        worker.isDaemon = true
        worker.start()
    }

    companion object {
        private const val TAG = "JarvisWebSocket"
        const val CONNECT_TIMEOUT_SECONDS = 10L
        const val READ_TIMEOUT_SECONDS = 60L
        const val HEARTBEAT_SECONDS = 20L
        const val MAX_RECONNECT_ATTEMPTS = 5
        const val BASE_BACKOFF_MS = 1000L
        const val MAX_BACKOFF_MS = 30000L
        const val NORMAL_CLOSURE = 1000
    }
}
