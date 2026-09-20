package com.friend.ios

import android.content.Intent
import com.friend.ios.batch.OmiBackgroundAudioStreamer
import com.friend.ios.ble.BleHostApiImpl
import com.friend.ios.ble.OmiBleForegroundService
import com.friend.ios.ble.OmiBleManager
import com.friend.ios.phonemic.*
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
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        localAudioImport?.accept(intent)
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
