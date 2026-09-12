import 'dart:async';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/pages/settings/selfhost_page.dart';

class LocalAudioShare {
  static const channel = MethodChannel('ollomi/audio_import');
  static bool _opening = false;
  static void initialize() {
    channel.setMethodCallHandler((call) async { if (call.method == 'available') await openPending(); });
    AuthService.instance.authStateChanges.listen((user) {
      if (user != null) WidgetsBinding.instance.addPostFrameCallback((_) => openPending());
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => openPending());
  }
  static Future<void> openPending() async {
    if (_opening || !AuthService.instance.isSignedIn()) return;
    final navigator = globalNavigatorKey.currentState;
    if (navigator == null) return;
    _opening = true;
    try {
      final files = await channel.invokeListMethod<String>('pending') ?? [];
      if (files.isNotEmpty) await navigator.push(MaterialPageRoute(builder: (_) => ImportAudioPage(sharedPaths: files)));
    } on MissingPluginException {
      // This import bridge is Android-only.
    } finally { _opening = false; }
  }
}
