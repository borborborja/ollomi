import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/background/background_capture_guard.dart';

void main() {
  test('only the foreground-service failure is a background capability warning', () {
    expect(BackgroundCaptureGuard.isBackgroundCapabilityWarning('foreground_service_failed'), isTrue);
    expect(BackgroundCaptureGuard.isBackgroundCapabilityWarning('batch_storage_full'), isFalse);
    expect(BackgroundCaptureGuard.isBackgroundCapabilityWarning('permission_denied'), isFalse);
  });

  test('battery warning fires on Android only, once, and while still optimized', () {
    bool shouldWarn({
      bool isAndroid = true,
      bool alreadyWarned = false,
      bool isIgnoring = false,
    }) =>
        BackgroundCaptureGuard.shouldWarnAboutBatteryOptimizations(
          isAndroid: isAndroid,
          alreadyWarned: alreadyWarned,
          isIgnoringBatteryOptimizations: isIgnoring,
        );

    expect(shouldWarn(), isTrue);
    expect(shouldWarn(isAndroid: false), isFalse);
    expect(shouldWarn(alreadyWarned: true), isFalse);
    expect(shouldWarn(isIgnoring: true), isFalse);
  });
}
