import 'package:flutter/services.dart';

import 'package:omi/services/widgets/widget_state.dart';
import 'package:omi/utils/logger.dart';

/// Dart side of the Android home-screen widget bridge (`com.ollomi.widgets`).
///
/// Dart owns the localized state; native owns rendering and the background
/// start/stop paths. Actions chosen in a widget reach Dart as
/// `onWidgetAction` (warm) or through [consumePendingAction] (cold start).
class WidgetBridge {
  static const MethodChannel _channel = MethodChannel('com.ollomi.widgets');

  Future<void> pushState(OllomiWidgetState state) async {
    try {
      await _channel.invokeMethod<bool>('updateState', {'state': state.encode()});
    } catch (e) {
      Logger.debug('WidgetBridge.pushState failed: $e');
    }
  }

  Future<String?> consumePendingAction() async {
    try {
      return await _channel.invokeMethod<String>('consumePendingAction');
    } catch (e) {
      Logger.debug('WidgetBridge.consumePendingAction failed: $e');
      return null;
    }
  }

  void setActionHandler(void Function(String action)? handler) {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onWidgetAction') {
        final action = call.arguments;
        if (action is String && action.isNotEmpty) {
          handler?.call(action);
        }
      }
      return null;
    });
  }
}
