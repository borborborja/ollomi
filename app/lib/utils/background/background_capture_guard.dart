/// Pure decisions for keeping capture alive while the app is in the background.
///
/// Kept free of platform calls so the policy is unit-testable; the callers own
/// the actual prompts.
class BackgroundCaptureGuard {
  const BackgroundCaptureGuard._();

  /// Native error emitted when the phone-mic foreground-service promotion was
  /// rejected (notification permission off, restricted OEM, ...). Capture keeps
  /// running foreground-only, so the UI must warn that the screen locking can
  /// interrupt it.
  static const String foregroundServiceFailedCode = 'foreground_service_failed';

  /// Codes that must reach the UI even in live mode (batch already surfaces all).
  static bool isBackgroundCapabilityWarning(String code) => code == foregroundServiceFailedCode;

  /// One-time nudge: Android kills background capture for battery-optimized apps,
  /// so ask before the first recording that may run with the screen off.
  static bool shouldWarnAboutBatteryOptimizations({
    required bool isAndroid,
    required bool alreadyWarned,
    required bool isIgnoringBatteryOptimizations,
  }) =>
      isAndroid && !alreadyWarned && !isIgnoringBatteryOptimizations;
}
