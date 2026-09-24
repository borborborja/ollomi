package com.friend.ios

import android.content.Intent
import com.friend.ios.batch.OmiBackgroundAudioStreamer
import com.friend.ios.ble.BleHostApiImpl
import com.friend.ios.ble.OmiBleForegroundService
import com.friend.ios.ble.OmiBleManager
import com.friend.ios.phonemic.*
import com.friend.ios.widgets.EXTRA_WIDGET_ACTION
import com.friend.ios.widgets.WidgetBridge
import com.friend.ios.widgets.WidgetPendingAction
import android.os.Bundle
import androidx.annotation.NonNull
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
    private var localAudioImport: LocalAudioImport? = null
    private val nativeBleTranscriptChannel = "com.friend.ios/native_ble_transcript"
    private var bleHostApiImpl: BleHostApiImpl? = null
    private var widgetBridge: WidgetBridge? = null

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        localAudioImport?.accept(intent)
        handleWidgetIntent(intent)
    }

    /** A widget tap that reached the activity: persist the action for a cold Dart
     *  start and notify Dart when the engine is already alive. */
    private fun handleWidgetIntent(intent: Intent?) {
        val action = intent?.getStringExtra(EXTRA_WIDGET_ACTION) ?: return
        intent.removeExtra(EXTRA_WIDGET_ACTION)
        WidgetPendingAction.set(this, action)
        widgetBridge?.notifyAction(action)
    }

    private val CHANNEL = "com.friend.ios/notifyOnKill"

    override fun configureFlutterEngine(@NonNull flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        localAudioImport = LocalAudioImport(this, flutterEngine.dartExecutor.binaryMessenger)
        localAudioImport?.accept(intent)

        // Register the native BLE Pigeon bridge before Dart starts device discovery.
        OmiBleManager.initialize(application)
        getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
            .edit()
            .putBoolean("flutter.nativeBleForegroundReady", false)
            .apply()
        OmiBleManager.isFlutterAlive = true
        OmiBleManager.instance.flutterApi = BleFlutterApi(flutterEngine.dartExecutor.binaryMessenger)
        val hostApi = BleHostApiImpl { this }
        hostApi.initCompanionManager(this)
        bleHostApiImpl = hostApi
        BleHostApi.setUp(flutterEngine.dartExecutor.binaryMessenger, hostApi)

        // Register Native Phone Mic Pigeon APIs
        PhoneMicController.initialize(application)
        PhoneMicController.instance.bindFlutterApi(PhoneMicFlutterApi(flutterEngine.dartExecutor.binaryMessenger))
        PhoneMicHostApi.setUp(flutterEngine.dartExecutor.binaryMessenger, PhoneMicHostApiImpl(PhoneMicController.instance))

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, nativeBleTranscriptChannel).setMethodCallHandler {
            call, result ->
            if (call.method == "drain") {
                result.success(OmiBackgroundAudioStreamer.drainCachedTranscriptMessages())
            } else {
                result.notImplemented()
            }
        }

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler {
            call, result ->
            if(call.method == "setNotificationOnKillService"){
                 val title = call.argument<String>("title")
                val description = call.argument<String>("description")

                val serviceIntent = Intent(this, NotificationOnKillService::class.java)

                serviceIntent.putExtra("title", title)
                serviceIntent.putExtra("description", description)

                startService(serviceIntent)
                result.success(true)
            }else{
                result.notImplemented()
            }
        }

        // Home-screen widgets: state in, actions out.
        widgetBridge = WidgetBridge(applicationContext, flutterEngine.dartExecutor.binaryMessenger)
        handleWidgetIntent(intent)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val address = bleHostApiImpl?.onActivityResult(requestCode, resultCode, data)
        if (address != null) {
            OmiBleForegroundService.startService(this, address, caller = "MainActivity.onActivityResult")
        }
    }

    override fun onResume() {
        super.onResume()
        OmiBleManager.isAppForeground = true
    }

    override fun onPause() {
        OmiBleManager.isAppForeground = false
        super.onPause()
    }

    override fun onDestroy() {
        OmiBleManager.isFlutterAlive = false
        getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
            .edit()
            .putBoolean("flutter.nativeBleForegroundReady", false)
            .apply()
        if (isFinishing) {
            if (PhoneMicController.isInitialized) PhoneMicController.instance.onFlutterEngineDestroyed()
            if (!OmiBleForegroundService.isPersistentModeEnabled(this)) {
                OmiBleForegroundService.stopService(this)
            }
        }
        super.onDestroy()
    }
}
