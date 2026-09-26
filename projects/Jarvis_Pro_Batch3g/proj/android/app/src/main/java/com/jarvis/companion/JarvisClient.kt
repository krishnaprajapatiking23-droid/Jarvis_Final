package com.jarvis.companion

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL

/**
 * REST client for pairing and one-shot commands (BUG 2).
 *
 * The hardcoded emulator loopback endpoint is gone: every call derives its
 * URL from the user-supplied ServerConfig, and the pairing token is sent
 * as a bearer header instead of being compiled into the app.
 */
class JarvisClient(private val config: ServerConfig) {

    data class Result(val code: Int, val body: String) {
        val isOk: Boolean
            get() = code in 200..299

        fun json(): JSONObject = try {
            JSONObject(body)
        } catch (error: Exception) {
            JSONObject().put("error", "Malformed response: " + error.message)
        }
    }

    /** Exchange the pairing secret for a scoped token. */
    fun login(pairingSecret: String, device: String): Result {
        val payload = JSONObject()
            .put("device", device)
            .put("pairing_secret", pairingSecret)
            .put(
                "scopes",
                JSONArray(listOf("command:read", "command:execute"))
            )
        return post("/api/login", payload, token = "")
    }

    /** Run a single command over HTTP (the WebSocket is used for sessions). */
    fun command(text: String): Result =
        post("/api/command", JSONObject().put("command", text), config.token)

    /** Check that the stored token is still valid. */
    fun verify(): Result = post("/api/verify", JSONObject(), config.token)

    private fun post(
        path: String,
        payload: JSONObject,
        token: String
    ): Result {
        val problem = config.validate()
        if (problem != null) {
            return Result(0, JSONObject().put("error", problem).toString())
        }

        var connection: HttpURLConnection? = null
        return try {
            val url = URL(config.httpUrl + path)
            connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = READ_TIMEOUT_MS
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                if (token.isNotBlank()) {
                    setRequestProperty("Authorization", "Bearer " + token)
                }
            }
            connection.outputStream.use {
                it.write(payload.toString().toByteArray())
            }
            val code = connection.responseCode
            val stream =
                if (code in 200..299) connection.inputStream
                else connection.errorStream
            val body = stream?.bufferedReader()?.use(BufferedReader::readText) ?: ""
            Result(code, body)
        } catch (error: Exception) {
            Result(
                0,
                JSONObject()
                    .put("error", error.message ?: "request failed")
                    .toString()
            )
        } finally {
            connection?.disconnect()
        }
    }

    companion object {
        const val CONNECT_TIMEOUT_MS = 5000
        const val READ_TIMEOUT_MS = 15000
    }
}
