import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('continuous capture defaults to off and phone source', () {
    expect(SharedPreferencesUtil().continuousCaptureEnabled, isFalse);
    expect(SharedPreferencesUtil().continuousCaptureSource, '');
  });

  test('continuous capture mode and source persist', () async {
    SharedPreferencesUtil().continuousCaptureEnabled = true;
    SharedPreferencesUtil().continuousCaptureSource = 'device';
    expect(SharedPreferencesUtil().continuousCaptureEnabled, isTrue);
    expect(SharedPreferencesUtil().continuousCaptureSource, 'device');
  });
}
