import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/device_connect_policy.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  BtDevice device(String id) => BtDevice(id: id, name: id, type: DeviceType.omi, rssi: -40);

  test('known-device policies default to auto-connect on and no recording', () {
    final prefs = SharedPreferencesUtil();
    expect(prefs.autoConnectEnabled, isTrue);
    expect(prefs.deviceAutoConnectFor('d1'), isTrue);
    expect(prefs.deviceRecordingOnConnectFor('d1'), DeviceRecordingOnConnect.none);
  });

  test('per-device policies persist independently', () async {
    final prefs = SharedPreferencesUtil();
    await prefs.setDeviceAutoConnectFor('d1', false);
    await prefs.setDeviceRecordingOnConnectFor('d1', DeviceRecordingOnConnect.continuous);
    expect(prefs.deviceAutoConnectFor('d1'), isFalse);
    expect(prefs.deviceRecordingOnConnectFor('d1'), DeviceRecordingOnConnect.continuous);
    expect(prefs.deviceAutoConnectFor('d2'), isTrue);
    expect(prefs.deviceRecordingOnConnectFor('d2'), DeviceRecordingOnConnect.none);
  });

  test('reorder changes the known-device priority order', () async {
    final prefs = SharedPreferencesUtil();
    await prefs.btDeviceSet(device('a'));
    await prefs.btDeviceSet(device('b'));
    await prefs.btDeviceSet(device('c'));
    await prefs.reorderKnownDevices(['c', 'a', 'b']);
    expect(prefs.btDevices.map((entry) => entry.id).toList(), ['c', 'a', 'b']);
  });

  test('forget removes the device and clears its settings', () async {
    final prefs = SharedPreferencesUtil();
    await prefs.btDeviceSet(device('a'));
    await prefs.setDeviceAliasFor('a', 'Casa');
    await prefs.setDeviceAutoConnectFor('a', false);
    await prefs.setDeviceRecordingOnConnectFor('a', DeviceRecordingOnConnect.oneOff);

    await prefs.forgetKnownDevice('a');

    expect(prefs.btDevices.any((entry) => entry.id == 'a'), isFalse);
    expect(prefs.deviceAliasFor('a'), '');
    expect(prefs.deviceAutoConnectFor('a'), isTrue); // back to the default
    expect(prefs.deviceRecordingOnConnectFor('a'), DeviceRecordingOnConnect.none);
  });

  test('auto-connect picks the highest-priority available device with the flag on', () async {
    final prefs = SharedPreferencesUtil();
    await prefs.btDeviceSet(device('high'));
    await prefs.btDeviceSet(device('low'));
    await prefs.setDeviceAutoConnectFor('high', false);

    final provider = DeviceProvider();
    addTearDown(provider.dispose);

    // 'high' has auto-connect off, so 'low' wins even when both are available.
    expect(provider.bestAutoConnectCandidate([device('high'), device('low')])?.id, 'low');

    await prefs.setDeviceAutoConnectFor('high', true);
    expect(provider.bestAutoConnectCandidate([device('high'), device('low')])?.id, 'high');

    // Unavailable devices are skipped; nothing is connected blind.
    expect(provider.bestAutoConnectCandidate([device('low')])?.id, 'low');
    expect(provider.bestAutoConnectCandidate([device('other')]), isNull);
  });

  test('the master switch disables auto-connect', () async {
    final prefs = SharedPreferencesUtil();
    await prefs.btDeviceSet(device('a'));
    prefs.autoConnectEnabled = false;

    final provider = DeviceProvider();
    addTearDown(provider.dispose);

    expect(provider.bestAutoConnectCandidate([device('a')]), isNull);
  });

  test('a manual disconnect suppresses auto-connect until cleared', () async {
    final prefs = SharedPreferencesUtil();
    await prefs.btDeviceSet(device('a'));

    final provider = DeviceProvider();
    addTearDown(provider.dispose);

    provider.suppressAutoConnect();
    expect(provider.discoveredKnownDevices, isEmpty);
    provider.clearAutoConnectSuppression();
    expect(provider.bestAutoConnectCandidate([device('a')])?.id, 'a');
  });
}
