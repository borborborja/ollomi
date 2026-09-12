package com.friend.ios

import android.app.Activity
import android.content.Intent
import android.net.Uri
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors

/** Copies explicitly shared audio into the app sandbox before exposing paths to Dart. */
class LocalAudioImport(private val activity: Activity, messenger: BinaryMessenger) {
    private val channel = MethodChannel(messenger, "ollomi/audio_import")
    private val executor = Executors.newSingleThreadExecutor()
    private val directory = File(activity.filesDir, "shared_audio").apply { mkdirs() }

    init {
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "pending" -> result.success(directory.listFiles()?.filter { it.extension != "part" }?.map { it.absolutePath } ?: emptyList<String>())
                "acknowledge" -> {
                    val paths = call.argument<List<String>>("paths") ?: emptyList()
                    paths.forEach { path ->
                        val file = File(path)
                        if (file.canonicalFile.parentFile == directory.canonicalFile) file.delete()
                    }
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    @Suppress("DEPRECATION")
    fun accept(intent: Intent?) {
        if (intent == null || intent.type?.startsWith("audio/") != true) return
        val uris = when (intent.action) {
            Intent.ACTION_SEND -> listOfNotNull(intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))
            Intent.ACTION_SEND_MULTIPLE -> intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.toList() ?: emptyList()
            else -> emptyList()
        }.filter { it.scheme == "content" }.take(20)
        intent.removeExtra(Intent.EXTRA_STREAM)
        executor.execute {
            uris.forEach { uri ->
                val id = UUID.randomUUID().toString()
                val temporary = File(directory, "$id.part")
                try {
                    activity.contentResolver.openInputStream(uri)?.use { source ->
                        temporary.outputStream().use { destination ->
                            val buffer = ByteArray(65536)
                            var count: Int
                            var total = 0L
                            while (source.read(buffer).also { count = it } > 0) {
                                total += count
                                require(total <= 1024L * 1024 * 1024) { "Audio exceeds 1 GiB" }
                                destination.write(buffer, 0, count)
                            }
                            destination.fd.sync()
                        }
                        check(temporary.renameTo(File(directory, "$id.audio")))
                    }
                } catch (_: Exception) {
                    temporary.delete()
                }
            }
            activity.runOnUiThread { channel.invokeMethod("available", null) }
        }
    }
}
