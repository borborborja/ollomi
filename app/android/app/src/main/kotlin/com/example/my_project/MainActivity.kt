package com.friend.ios

import android.content.Intent
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

        // Register Native Phone Mic Pigeon APIs
        PhoneMicController.initialize(application)
        PhoneMicController.instance.bindFlutterApi(PhoneMicFlutterApi(flutterEngine.dartExecutor.binaryMessenger))
        PhoneMicHostApi.setUp(flutterEngine.dartExecutor.binaryMessenger, PhoneMicHostApiImpl(PhoneMicController.instance))

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

    override fun onDestroy() {
        if (isFinishing) {
            if (PhoneMicController.isInitialized) PhoneMicController.instance.onFlutterEngineDestroyed()
        }
        super.onDestroy()
    }
}
