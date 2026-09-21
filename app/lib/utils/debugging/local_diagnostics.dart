import 'package:flutter/material.dart';
import 'package:omi/utils/logger.dart';

/// Local diagnostics for upstream call sites. Never sends data to a service.
class LocalDiagnostics {
  static final instance = LocalDiagnostics();

  static Future<void> init() async {}

  void identifyUser(String email, String name, String userId) {}
  void logInfo(String message) => Logger.info(message);
  void logError(String message) => Logger.error(message);
  void logWarn(String message) => Logger.warning(message);
  void logDebug(String message) => Logger.debug(message);
  void logVerbose(String message) => Logger.debug(message);
  void setUserAttribute(String key, String value) {}
  void setEnabled(bool enabled) {}
  Future<void> reportCrash(Object exception, StackTrace stackTrace, {Map<String, String>? userAttributes}) async =>
      Logger.handle(exception, stackTrace);
  NavigatorObserver? getNavigatorObserver() => null;
  bool get isSupported => true;
}
