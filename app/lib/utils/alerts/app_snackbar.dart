import 'package:flutter/material.dart';

import 'package:omi/app_globals.dart';

class AppSnackbar {
  static void showSnackbar(String message, {Color? color, Duration? duration, SnackBarAction? action}) {
    ScaffoldMessenger.of(globalNavigatorKey.currentState!.context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color,
        duration: duration ?? const Duration(seconds: 2),
        action: action,
      ),
    );
  }

  static void showSnackbarError(String message, {Duration? duration}) {
    showSnackbar(message, color: Colors.red, duration: duration);
  }

  static void showSnackbarSuccess(String message, {Duration? duration}) {
    showSnackbar(message, color: Colors.green.shade700, duration: duration);
  }

  /// Snackbar with a single action button (e.g. "open the battery settings").
  static void showActionSnackbar(
    String message, {
    required String actionLabel,
    required VoidCallback onAction,
    Duration? duration,
  }) {
    showSnackbar(message, duration: duration, action: SnackBarAction(label: actionLabel, onPressed: onAction));
  }
}
