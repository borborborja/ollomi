import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/device.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('device alias storage', () {
    test('returns empty when no alias is set', () {
      expect(SharedPreferencesUtil().deviceAliasFor('dev-1'), '');
    });

    test('stores and trims an alias per device id', () async {
      await SharedPreferencesUtil().setDeviceAliasFor('dev-1', '  Omi de casa  ');
      expect(SharedPreferencesUtil().deviceAliasFor('dev-1'), 'Omi de casa');
      expect(SharedPreferencesUtil().deviceAliasFor('dev-2'), '');
    });

    test('a blank value clears the alias', () async {
      await SharedPreferencesUtil().setDeviceAliasFor('dev-1', 'Casa');
      await SharedPreferencesUtil().setDeviceAliasFor('dev-1', '   ');
      expect(SharedPreferencesUtil().deviceAliasFor('dev-1'), '');
    });

    test('an empty device id is ignored', () async {
      await SharedPreferencesUtil().setDeviceAliasFor('', 'Casa');
      expect(SharedPreferencesUtil().deviceAliasFor(''), '');
    });
  });

  group('device display name', () {
    final device = BtDevice(id: 'dev-1', name: 'Omi CV 1', type: DeviceType.omi, rssi: -40);

    test('falls back to the advertised name when no alias is set', () {
      expect(DeviceUtils.aliasFor(device), isNull);
      expect(DeviceUtils.displayName(device, fallback: 'Omi DevKit'), 'Omi CV 1');
    });

    test('prefers the alias when set', () async {
      await SharedPreferencesUtil().setDeviceAliasFor(device.id, 'Casa');
      expect(DeviceUtils.aliasFor(device), 'Casa');
      expect(DeviceUtils.displayName(device, fallback: 'Omi DevKit'), 'Casa');
    });

    test('uses the fallback for a null device', () {
      expect(DeviceUtils.aliasFor(null), isNull);
      expect(DeviceUtils.displayName(null, fallback: 'Omi DevKit'), 'Omi DevKit');
    });

    test('keeps aliases independent across devices', () async {
      final other = BtDevice(id: 'dev-2', name: 'Friend', type: DeviceType.friendPendant, rssi: -50);
      await SharedPreferencesUtil().setDeviceAliasFor(device.id, 'Casa');
      expect(DeviceUtils.displayName(device), 'Casa');
      expect(DeviceUtils.displayName(other), 'Friend');
    });
  });
}
