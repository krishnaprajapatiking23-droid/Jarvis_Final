package com.jarvis.companion

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * User-editable server configuration (BUG 2).
 *
 * The hardcoded emulator loopback address is gone. Host, port, token and TLS are
 * entered by the user and persisted in EncryptedSharedPreferences, so no
 * credential is hardcoded and no subnet is assumed.
 */
data class ServerConfig(
    val host: String = "",
    val port: Int = DEFAULT_PORT,
    val token: String = "",
    val useTls: Boolean = false
) {

    val hostPort: String
        get() = host + ":" + port

    val webSocketUrl: String
        get() = (if (useTls) "wss://" else "ws://") + hostPort + WS_PATH

    val httpUrl: String
        get() = (if (useTls) "https://" else "http://") + hostPort

    val isConfigured: Boolean
        get() = validate() == null

    val isPaired: Boolean
        get() = token.isNotBlank()

    /** Returns a human-readable problem, or null when the config is usable. */
    fun validate(): String? {
        if (host.isBlank()) return "Enter the PC host name or IP address"
        if (host.contains("/") || host.contains(" ")) {
            return "Host must not contain spaces or slashes"
        }
        if (port !in 1..65535) return "Port must be between 1 and 65535"
        return null
    }

    companion object {
        const val DEFAULT_PORT = 8765
        const val WS_PATH = "/ws"

        private const val FILE = "jarvis_server_config"
        private const val KEY_HOST = "host"
        private const val KEY_PORT = "port"
        private const val KEY_TOKEN = "token"
        private const val KEY_TLS = "use_tls"

        private fun preferences(context: Context) =
            EncryptedSharedPreferences.create(
                context,
                FILE,
                MasterKey.Builder(context)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build(),
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )

        /** Load the saved configuration, or an empty one on first run. */
        fun load(context: Context): ServerConfig {
            val prefs = preferences(context)
            return ServerConfig(
                host = prefs.getString(KEY_HOST, "") ?: "",
                port = prefs.getInt(KEY_PORT, DEFAULT_PORT),
                token = prefs.getString(KEY_TOKEN, "") ?: "",
                useTls = prefs.getBoolean(KEY_TLS, false)
            )
        }

        /** Persist the configuration, including the pairing token. */
        fun save(context: Context, config: ServerConfig) {
            preferences(context).edit()
                .putString(KEY_HOST, config.host)
                .putInt(KEY_PORT, config.port)
                .putString(KEY_TOKEN, config.token)
                .putBoolean(KEY_TLS, config.useTls)
                .apply()
        }

        /** Forget the pairing token without losing host/port. */
        fun clearToken(context: Context) {
            preferences(context).edit().remove(KEY_TOKEN).apply()
        }
    }
}
