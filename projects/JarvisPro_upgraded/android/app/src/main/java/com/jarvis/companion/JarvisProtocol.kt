package com.jarvis.companion

import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

/**
 * Structured JSON envelope shared with the PC server (Phase 6).
 *
 * Requests:  {"type":..., "id":..., "timestamp":..., "payload":{...}}
 * Responses: {"id":..., "type":..., "status":..., "payload":{}, "error":...}
 */
object JarvisProtocol {

    const val TYPE_AUTH = "auth"
    const val TYPE_COMMAND = "command"
    const val TYPE_PING = "ping"
    const val TYPE_PONG = "pong"

    const val STATUS_OK = "ok"
    const val STATUS_ERROR = "error"

    private fun timestamp(): String {
        val format = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
        format.timeZone = TimeZone.getTimeZone("UTC")
        return format.format(Date())
    }

    fun newId(): String = UUID.randomUUID().toString()

    fun envelope(
        type: String,
        payload: JSONObject,
        id: String = newId()
    ): JSONObject =
        JSONObject()
            .put("type", type)
            .put("id", id)
            .put("timestamp", timestamp())
            .put("payload", payload)

    /** Authenticate the socket with the stored pairing token. */
    fun auth(token: String, device: String): JSONObject =
        envelope(
            TYPE_AUTH,
            JSONObject().put("token", token).put("device", device)
        )

    /** Send a natural-language command. */
    fun command(text: String): JSONObject =
        envelope(TYPE_COMMAND, JSONObject().put("text", text))

    /** Heartbeat frame. */
    fun ping(): JSONObject = envelope(TYPE_PING, JSONObject())

    data class Response(
        val id: String,
        val type: String,
        val status: String,
        val payload: JSONObject,
        val error: String
    ) {
        val isOk: Boolean
            get() = status == STATUS_OK && error.isEmpty()

        /** Best-effort human-readable text from the payload. */
        fun text(): String {
            for (key in listOf("reply", "text", "message", "result")) {
                val value = payload.optString(key, "")
                if (value.isNotBlank()) return value
            }
            return payload.toString()
        }
    }

    /** Parse a server frame; malformed input becomes an error response. */
    fun parse(frame: String): Response {
        return try {
            val json = JSONObject(frame)
            val fallback = if (json.has("error")) STATUS_ERROR else STATUS_OK
            Response(
                id = json.optString("id", ""),
                type = json.optString("type", ""),
                status = json.optString("status", fallback),
                payload = json.optJSONObject("payload") ?: JSONObject(),
                error = json.optString("error", "")
            )
        } catch (error: Exception) {
            Response(
                id = "",
                type = "",
                status = STATUS_ERROR,
                payload = JSONObject(),
                error = "Malformed server frame: " + error.message
            )
        }
    }
}
