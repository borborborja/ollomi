import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('active capture button behavior defaults safely and persists every option', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final preferences = SharedPreferencesUtil();

    expect(preferences.activeCaptureButtonBehavior, ActiveCaptureButtonBehavior.openActive);

    for (final behavior in ActiveCaptureButtonBehavior.values) {
      preferences.activeCaptureButtonBehavior = behavior;
      expect(preferences.activeCaptureButtonBehavior, behavior);
    }
  });

  test('unknown stored behavior falls back to opening the active recording', () async {
    SharedPreferences.setMockInitialValues({'activeCaptureButtonBehavior': 'future_value'});
    await SharedPreferencesUtil.init();

    expect(
      SharedPreferencesUtil().activeCaptureButtonBehavior,
      ActiveCaptureButtonBehavior.openActive,
    );
  });
}
