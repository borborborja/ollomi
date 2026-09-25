import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/devices_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider({this.connected, this.paired, Set<String>? available}) : _available = available ?? {};

  final BtDevice? connected;
  final BtDevice? paired;
  final Set<String> _available;
  final List<String> connectedTo = [];
  int refreshCalls = 0;

  @override
  BtDevice? get connectedDevice => connected;

  @override
  BtDevice? get pairedDevice => paired;

  @override
  bool isDeviceAvailable(String deviceId) => _available.contains(deviceId);

  @override
  Future<void> refreshKnownDeviceAvailability() async => refreshCalls++;

  @override
  void clearAutoConnectSuppression() {}

  @override
  void suppressAutoConnect() {}

  @override
  void setIsConnected(bool value) {}

  @override
  Future<void> setConnectedDevice(BtDevice? device) async {}

  @override
  void updateConnectingStatus(bool value) {}

  @override
  Future<void> connectToKnownDevice(BtDevice device, {bool confirmedStop = false}) async {
    connectedTo.add(device.id);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _app(DeviceProvider provider, CaptureProvider capture) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<DeviceProvider>.value(value: provider),
      ChangeNotifierProvider<CaptureProvider>.value(value: capture),
    ],
    child: const MaterialApp(
      localizationsDelegates: [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: DevicesPage(),
    ),
  );
}

void main() {
  final near = BtDevice(id: 'near', name: 'Casa', type: DeviceType.omi, rssi: -40);
  final far = BtDevice(id: 'far', name: 'Cotxe', type: DeviceType.omi, rssi: -70);

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('lists known devices in order with auto-connect and policy controls', (tester) async {
    final preferences = SharedPreferencesUtil();
    await preferences.btDeviceSet(near);
    await preferences.btDeviceSet(far);

    final provider = _StubDeviceProvider(connected: near, paired: near, available: {'far'});
    final capture = CaptureProvider();
    addTearDown(provider.dispose);
    addTearDown(capture.dispose);

    await tester.pumpWidget(_app(provider, capture));
    await tester.pump();

    expect(find.text('Casa'), findsOneWidget);
    expect(find.text('Cotxe'), findsOneWidget);
    expect(find.byKey(const Key('device_auto_connect_near')), findsOneWidget);
    expect(find.byKey(const Key('device_recording_policy_far')), findsOneWidget);
    expect(provider.refreshCalls, greaterThanOrEqualTo(1));
  });

  testWidgets('connecting a non-active device asks the provider', (tester) async {
    final preferences = SharedPreferencesUtil();
    await preferences.btDeviceSet(near);
    await preferences.btDeviceSet(far);

    final provider = _StubDeviceProvider(connected: near, paired: near, available: {'far'});
    final capture = CaptureProvider();
    addTearDown(provider.dispose);
    addTearDown(capture.dispose);

    await tester.pumpWidget(_app(provider, capture));
    await tester.pump();

    await tester.tap(find.byKey(const Key('device_connect_far')));
    await tester.pump();

    expect(provider.connectedTo, ['far']);
  });

  testWidgets('the master auto-connect switch persists', (tester) async {
    final preferences = SharedPreferencesUtil();
    await preferences.btDeviceSet(near);

    final provider = _StubDeviceProvider(connected: null, paired: null, available: {'near'});
    final capture = CaptureProvider();
    addTearDown(provider.dispose);
    addTearDown(capture.dispose);

    await tester.pumpWidget(_app(provider, capture));
    await tester.pump();

    await tester.tap(find.byKey(const Key('auto_connect_master_switch')));
    await tester.pump();

    expect(SharedPreferencesUtil().autoConnectEnabled, isFalse);
  });
}
