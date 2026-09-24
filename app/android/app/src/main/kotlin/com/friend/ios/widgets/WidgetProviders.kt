package com.friend.ios.widgets

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.os.SystemClock
import android.view.View
import android.widget.RemoteViews

import com.friend.ios.R

/** Which surface a widget shows. All four share one adaptive layout. */
enum class WidgetKind {
    RECORD,
    TRANSCRIPT,
    DEVICE,
    COMBINED,
}

/**
 * Renders the home-screen widgets from [WidgetState] and keeps them in sync.
 *
 * RemoteViews only supports a small view vocabulary, so state is reduced to a
 * dot, two labels, a Chronometer, two transcript lines, one device line and up
 * to four action buttons; [WidgetKind] decides which sections are shown.
 */
object WidgetRenderer {
    private const val DOT_RECORDING = 0xFFFE5D50.toInt()
    private const val DOT_IDLE = 0xFF3C3C43.toInt()

    fun build(context: Context, kind: WidgetKind, state: WidgetState): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.widget_ollomi)

        views.setInt(R.id.widget_dot, "setBackgroundColor", if (state.recording) DOT_RECORDING else DOT_IDLE)

        val title = if (state.recording) {
            state.source.ifEmpty { state.labelContinuous }
        } else {
            state.labelIdle
        }
        views.setTextViewText(R.id.widget_title, title)

        val subtitle = when {
            state.recording && state.continuous -> state.labelContinuous
            state.recording -> state.labelOneOff
            else -> ""
        }
        views.setTextViewText(R.id.widget_subtitle, subtitle)
        views.setViewVisibility(R.id.widget_subtitle, if (subtitle.isEmpty()) View.GONE else View.VISIBLE)

        if (state.recording && state.startedAt > 0L) {
            val base = SystemClock.elapsedRealtime() - (System.currentTimeMillis() - state.startedAt)
            views.setChronometer(R.id.widget_timer, base, null, true)
            views.setViewVisibility(R.id.widget_timer, View.VISIBLE)
        } else {
            views.setChronometer(R.id.widget_timer, SystemClock.elapsedRealtime(), null, false)
            views.setViewVisibility(R.id.widget_timer, View.GONE)
        }

        bindTranscript(views, kind, state)
        bindDevice(views, kind, state)
        bindActions(context, views, kind, state)
        return views
    }

    private fun bindTranscript(views: RemoteViews, kind: WidgetKind, state: WidgetState) {
        val showsLines = kind == WidgetKind.TRANSCRIPT || kind == WidgetKind.COMBINED
        val lines = state.transcriptLines
        val first = if (showsLines) lines.getOrNull(0) ?: state.transcriptState else ""
        val second = if (showsLines) {
            lines.getOrNull(1) ?: if (lines.isNotEmpty()) state.transcriptState else ""
        } else {
            ""
        }
        views.setTextViewText(R.id.widget_line1, first)
        views.setViewVisibility(R.id.widget_line1, if (first.isEmpty()) View.GONE else View.VISIBLE)
        views.setTextViewText(R.id.widget_line2, second)
        views.setViewVisibility(R.id.widget_line2, if (second.isEmpty()) View.GONE else View.VISIBLE)
    }

    private fun bindDevice(views: RemoteViews, kind: WidgetKind, state: WidgetState) {
        val showsDevice = kind == WidgetKind.DEVICE || kind == WidgetKind.COMBINED
        val battery = if (state.deviceBattery in 0..100) " · ${state.deviceBattery}%" else ""
        val text = if (showsDevice && state.deviceName.isNotEmpty()) "${state.deviceName}$battery" else ""
        views.setTextViewText(R.id.widget_device, text)
        views.setViewVisibility(R.id.widget_device, if (text.isEmpty()) View.GONE else View.VISIBLE)
    }

    private fun bindActions(context: Context, views: RemoteViews, kind: WidgetKind, state: WidgetState) {
        val oneOff = WidgetActionReceiver.pendingIntent(context, WidgetAction.START_ONE_OFF, 1)
        val continuous = WidgetActionReceiver.pendingIntent(context, WidgetAction.START_CONTINUOUS, 2)
        val stop = WidgetActionReceiver.pendingIntent(context, WidgetAction.STOP, 3)
        val connect = WidgetActionReceiver.pendingIntent(context, WidgetAction.CONNECT_DEVICE, 4)
        val openTranscript = WidgetActionReceiver.pendingIntent(context, WidgetAction.OPEN_TRANSCRIPT, 5)

        views.setTextViewText(R.id.widget_action_one_off, state.labelOneOff)
        views.setTextViewText(R.id.widget_action_continuous, state.labelContinuous)
        views.setTextViewText(R.id.widget_action_stop, state.labelStop)
        views.setTextViewText(R.id.widget_action_connect, state.labelConnect)
        views.setOnClickPendingIntent(R.id.widget_action_one_off, oneOff)
        views.setOnClickPendingIntent(R.id.widget_action_continuous, continuous)
        views.setOnClickPendingIntent(R.id.widget_action_stop, stop)
        views.setOnClickPendingIntent(R.id.widget_action_connect, connect)
        views.setOnClickPendingIntent(R.id.widget_root, openTranscript)

        val showsRecordActions = kind == WidgetKind.RECORD || kind == WidgetKind.COMBINED
        views.setViewVisibility(
            R.id.widget_action_one_off,
            if (showsRecordActions && !state.recording) View.VISIBLE else View.GONE,
        )
        views.setViewVisibility(
            R.id.widget_action_continuous,
            if (showsRecordActions && !state.recording) View.VISIBLE else View.GONE,
        )
        views.setViewVisibility(
            R.id.widget_action_stop,
            if (showsRecordActions && state.recording) View.VISIBLE else View.GONE,
        )
        val showsConnect = kind == WidgetKind.DEVICE || kind == WidgetKind.COMBINED
        views.setViewVisibility(R.id.widget_action_connect, if (showsConnect) View.VISIBLE else View.GONE)
    }

    fun kindFor(provider: Class<out AppWidgetProvider>): WidgetKind = when (provider) {
        RecordWidgetProvider::class.java -> WidgetKind.RECORD
        TranscriptWidgetProvider::class.java -> WidgetKind.TRANSCRIPT
        DeviceWidgetProvider::class.java -> WidgetKind.DEVICE
        else -> WidgetKind.COMBINED
    }

    fun update(context: Context, provider: Class<out AppWidgetProvider>, state: WidgetState) {
        val manager = AppWidgetManager.getInstance(context)
        val ids = manager.getAppWidgetIds(ComponentName(context, provider))
        val kind = kindFor(provider)
        for (id in ids) {
            manager.updateAppWidget(id, build(context, kind, state))
        }
    }
}

object WidgetProviders {
    private val providers = listOf(
        RecordWidgetProvider::class.java,
        TranscriptWidgetProvider::class.java,
        DeviceWidgetProvider::class.java,
        CombinedWidgetProvider::class.java,
    )

    fun refreshAll(context: Context) {
        val state = WidgetStateStore.read(context)
        for (provider in providers) {
            WidgetRenderer.update(context, provider, state)
        }
    }
}

class RecordWidgetProvider : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val state = WidgetStateStore.read(context)
        for (id in ids) {
            manager.updateAppWidget(id, WidgetRenderer.build(context, WidgetKind.RECORD, state))
        }
    }
}

class TranscriptWidgetProvider : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val state = WidgetStateStore.read(context)
        for (id in ids) {
            manager.updateAppWidget(id, WidgetRenderer.build(context, WidgetKind.TRANSCRIPT, state))
        }
    }
}

class DeviceWidgetProvider : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val state = WidgetStateStore.read(context)
        for (id in ids) {
            manager.updateAppWidget(id, WidgetRenderer.build(context, WidgetKind.DEVICE, state))
        }
    }
}

class CombinedWidgetProvider : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val state = WidgetStateStore.read(context)
        for (id in ids) {
            manager.updateAppWidget(id, WidgetRenderer.build(context, WidgetKind.COMBINED, state))
        }
    }
}
