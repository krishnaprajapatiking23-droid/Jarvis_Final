package com.jarvis.companion

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.util.concurrent.Executors

/**
 * Connection screen for the Jarvis companion (Phase 6).
 *
 * Host, port and TLS are user-editable; the pairing secret is exchanged for
 * a token that is stored encrypted. Every network call runs on a worker
 * executor, never on the UI thread.
 */
class MainActivity : Activity() {

    private lateinit var hostField: EditText
    private lateinit var portField: EditText
    private lateinit var secretField: EditText
    private lateinit var commandField: EditText
    private lateinit var tlsBox: CheckBox
    private lateinit var statusView: TextView
    private lateinit var logView: TextView

    private val worker = Executors.newSingleThreadExecutor()
    private val ui = Handler(Looper.getMainLooper())
    private var socket: JarvisWebSocketClient? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val saved = ServerConfig.load(this)

        val root = LinearLayout(this)
        root.orientation = LinearLayout.VERTICAL
        root.setPadding(32, 48, 32, 32)

        statusView = TextView(this)
        statusView.text = status(ConnectionState.DISCONNECTED, "")
        root.addView(statusView)

        hostField = EditText(this)
        hostField.hint = "PC host or IP (for example 192.168.0.42)"
        hostField.setText(saved.host)
        hostField.inputType =
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        root.addView(hostField)

        portField = EditText(this)
        portField.hint = "Port"
        portField.setText(saved.port.toString())
        portField.inputType = InputType.TYPE_CLASS_NUMBER
        root.addView(portField)

        tlsBox = CheckBox(this)
        tlsBox.text = "Use TLS (wss://)"
        tlsBox.isChecked = saved.useTls
        root.addView(tlsBox)

        secretField = EditText(this)
        secretField.hint = "Pairing secret (not stored)"
        secretField.inputType =
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        root.addView(secretField)

        root.addView(button("Discover servers on this network") { discover() })
        root.addView(button("Pair") { pair() })
        root.addView(button("Connect") { connect() })
        root.addView(button("Disconnect") { socket?.disconnect() })

        commandField = EditText(this)
        commandField.hint = "Say something to Jarvis"
        root.addView(commandField)
        root.addView(button("Send") { send() })

        logView = TextView(this)
        val scroller = ScrollView(this)
        scroller.addView(logView)
        scroller.layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            0
        ).apply { weight = 1f }
        root.addView(scroller)

        setContentView(root)

        if (saved.isPaired) {
            log("Saved pairing found for " + saved.hostPort)
        }
    }

    override fun onDestroy() {
        socket?.disconnect()
        worker.shutdownNow()
        super.onDestroy()
    }

    private fun button(label: String, action: () -> Unit): Button {
        val view = Button(this)
        view.text = label
        view.setOnClickListener { action() }
        return view
    }

    private fun status(state: ConnectionState, detail: String): String {
        val label = when (state) {
            ConnectionState.DISCONNECTED -> "Disconnected"
            ConnectionState.CONNECTING -> "Connecting"
            ConnectionState.CONNECTED -> "Connected"
            ConnectionState.AUTH_FAILED -> "Authentication Failed"
            ConnectionState.SERVER_UNAVAILABLE -> "Server Unavailable"
            ConnectionState.TIMEOUT -> "Timeout"
        }
        return if (detail.isBlank()) {
            "Status: " + label
        } else {
            "Status: " + label + " - " + detail
        }
    }

    /** Read the form into a config, keeping the stored token. */
    private fun readConfig(): ServerConfig {
        val stored = ServerConfig.load(this)
        val port = portField.text.toString().trim().toIntOrNull()
        return ServerConfig(
            host = hostField.text.toString().trim(),
            port = port ?: ServerConfig.DEFAULT_PORT,
            token = stored.token,
            useTls = tlsBox.isChecked
        )
    }

    private fun discover() {
        log("Searching the local network...")
        worker.execute {
            val servers = DiscoveryClient.discover()
            ui.post {
                if (servers.isEmpty()) {
                    log("No servers advertised. Enter the host manually.")
                } else {
                    val first = servers.first()
                    hostField.setText(first.host)
                    portField.setText(first.port.toString())
                    tlsBox.isChecked = first.useTls
                    log(
                        "Found " + servers.size + " server(s); selected " +
                            first.name + " at " + first.host + ":" + first.port
                    )
                }
            }
        }
    }

    private fun pair() {
        val config = readConfig()
        val problem = config.validate()
        if (problem != null) {
            log(problem)
            return
        }
        val secret = secretField.text.toString()
        if (secret.isBlank()) {
            log("Enter the pairing secret shown by the PC server.")
            return
        }
        log("Pairing with " + config.hostPort + "...")
        val device = android.os.Build.MODEL ?: "Android"
        worker.execute {
            val result = JarvisClient(config).login(secret, device)
            val token = result.json().optString("token", "")
            ui.post {
                if (result.isOk && token.isNotBlank()) {
                    ServerConfig.save(this, config.copy(token = token))
                    secretField.setText("")
                    log("Paired. Token stored encrypted on this device.")
                } else {
                    statusView.text = status(ConnectionState.AUTH_FAILED, "")
                    log(
                        "Pairing failed: " +
                            result.json().optString("error", result.body)
                    )
                }
            }
        }
    }

    private fun connect() {
        val config = readConfig()
        val problem = config.validate()
        if (problem != null) {
            log(problem)
            return
        }
        ServerConfig.save(this, config)
        socket?.disconnect()
        socket = JarvisWebSocketClient(
            config = config,
            deviceName = android.os.Build.MODEL ?: "Android",
            onState = { state, detail ->
                ui.post {
                    statusView.text = status(state, detail)
                    log(status(state, detail))
                }
            },
            onMessage = { response ->
                ui.post {
                    if (response.isOk) {
                        log("Jarvis: " + response.text())
                    } else {
                        log("Error: " + response.error)
                    }
                }
            }
        )
        socket?.connect()
    }

    private fun send() {
        val text = commandField.text.toString().trim()
        if (text.isEmpty()) return
        val active = socket
        if (active == null || !active.sendCommand(text)) {
            log("Not connected - press Connect first.")
            return
        }
        log("You: " + text)
        commandField.setText("")
    }

    private fun log(line: String) {
        logView.append(line + "\n")
    }
}
