import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/enums.dart';

class _DisconnectedDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  int get batteryLevel => -1;

  @override
  BtDevice? get connectedDevice => null;

  @override
  bool get isCharging => false;

  @override
  bool get isConnecting => false;

  @override
  BtDevice? get pairedDevice => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RecordingCaptureProvider extends CaptureProvider {
  int stopCalls = 0;

  @override
  Future<void> stopCurrentCapture() async {
    stopCalls++;
  }
}
void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pumpActiveButton(WidgetTester tester, CaptureProvider captureProvider) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
          ChangeNotifierProvider<DeviceProvider>.value(value: _DisconnectedDeviceProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: const Scaffold(body: HomeRecordButton()),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('idle one-off capture shows the add button', (tester) async {
    SharedPreferencesUtil().continuousCaptureEnabled = false;
    final captureProvider = CaptureProvider()..updateRecordingState(RecordingState.stop);
    addTearDown(captureProvider.dispose);
    await pumpActiveButton(tester, captureProvider);

    expect(find.byKey(const Key('home-record-button-surface')), findsOneWidget);
    expect(find.byIcon(Icons.add), findsOneWidget);
    expect(find.byIcon(Icons.stop_rounded), findsNothing);
  });

  testWidgets('recording turns the button into a finish action for every legacy behavior', (tester) async {
    // The button's active state no longer depends on the retired
    // ActiveCaptureButtonBehavior setting: it is always finish.
    for (final behavior in [ActiveCaptureButtonBehavior.openActive, ActiveCaptureButtonBehavior.switchSource]) {
      SharedPreferencesUtil().activeCaptureButtonBehavior = behavior;
      SharedPreferencesUtil().continuousCaptureEnabled = false;
      final captureProvider = _RecordingCaptureProvider()..updateRecordingState(RecordingState.record);
      addTearDown(captureProvider.dispose);
      await pumpActiveButton(tester, captureProvider);

      expect(find.byKey(const Key('home-record-button-surface')), findsOneWidget);
      expect(find.byIcon(Icons.stop_rounded), findsOneWidget, reason: 'active one-off capture must offer finish');
      expect(find.byIcon(Icons.add), findsNothing);

      await tester.tap(find.byKey(const Key('home-record-button-surface')));
      await tester.pump();
      expect(captureProvider.stopCalls, 1, reason: 'tap while recording finishes the capture');
    }
  });

  testWidgets('continuous mode keeps the one-off button hidden, idle or recording', (tester) async {
    SharedPreferencesUtil().activeCaptureButtonBehavior = ActiveCaptureButtonBehavior.openActive;
    SharedPreferencesUtil().continuousCaptureEnabled = true;

    final idleProvider = CaptureProvider()..updateRecordingState(RecordingState.stop);
    addTearDown(idleProvider.dispose);
    await pumpActiveButton(tester, idleProvider);
    expect(find.byKey(const Key('home-record-button-surface')), findsNothing);

    final recordingProvider = _RecordingCaptureProvider()..updateRecordingState(RecordingState.record);
    addTearDown(recordingProvider.dispose);
    await pumpActiveButton(tester, recordingProvider);
    expect(
      find.byKey(const Key('home-record-button-surface')),
      findsNothing,
      reason: 'the top-bar switch owns continuous mode',
    );
  });

  testWidgets('initialising shows progress instead of a tappable action', (tester) async {
    SharedPreferencesUtil().continuousCaptureEnabled = false;
    final captureProvider = CaptureProvider()..updateRecordingState(RecordingState.initialising);
    addTearDown(captureProvider.dispose);
    await pumpActiveButton(tester, captureProvider);

    expect(find.byKey(const Key('home-record-button-surface')), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byIcon(Icons.stop_rounded), findsNothing);
    expect(find.byIcon(Icons.add), findsNothing);
  });

  testWidgets('long-press opens the record options sheet with import audio', (tester) async {
    SharedPreferencesUtil().continuousCaptureEnabled = false;
    final captureProvider = CaptureProvider()..updateRecordingState(RecordingState.stop);
    addTearDown(captureProvider.dispose);
    await pumpActiveButton(tester, captureProvider);

    await tester.longPress(find.byKey(const Key('home-record-button-surface')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('record-source-phone-mic')), findsOneWidget);
    expect(find.byKey(const Key('record-source-connect-device')), findsOneWidget);
    expect(find.byKey(const Key('record-source-import-audio')), findsOneWidget);
  });

  // Regression test: FaIcon (unlike material Icon) has no internal Center, so
  // without an alignment on the fixed-size circle container the glyph painted
  // at the top-left, outside the circle.
  testWidgets('record option icons are centered inside their circles', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: RecordOptionsSheet(
            onPickPhoneMic: () {},
            onPickPhoneCall: () {},
            connectedDeviceName: 'Omi',
            onPickConnectedDevice: () {},
            onImportAudio: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final icons = find.byType(FaIcon);
    expect(icons, findsNWidgets(4));

    for (final icon in icons.evaluate()) {
      final iconRect = tester.getRect(find.byWidget(icon.widget));
      final circle = find.ancestor(of: find.byWidget(icon.widget), matching: find.byType(Container)).first;
      final circleRect = tester.getRect(circle);

      expect(circleRect.size, const Size(44, 44));
      // Without the fix the circle passes tight 44x44 constraints to the
      // FaIcon, whose glyph then paints at the top-left, outside the circle.
      // With alignment set, constraints are loosened: the icon's render box
      // keeps its natural ~18px size and is centered inside the circle.
      expect(iconRect.width, lessThan(circleRect.width), reason: 'icon box inflated by tight constraints');
      expect(iconRect.height, lessThan(circleRect.height), reason: 'icon box inflated by tight constraints');
      expect(iconRect.center.dx, closeTo(circleRect.center.dx, 0.5));
      expect(iconRect.center.dy, closeTo(circleRect.center.dy, 0.5));
    }
  });

  testWidgets('record options expose connected-device and audio-import sources', (tester) async {
    var deviceSelected = false;
    var importSelected = false;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: RecordOptionsSheet(
            onPickPhoneMic: () {},
            onPickPhoneCall: () {},
            connectedDeviceName: 'Friend Pendant',
            onPickConnectedDevice: () => deviceSelected = true,
            onImportAudio: () => importSelected = true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Record: Friend Pendant'), findsOneWidget);
    expect(find.text('Import Data: Recordings'), findsOneWidget);
    expect(find.text('MP3 · M4A · WAV · OGG · FLAC'), findsOneWidget);

    await tester.tap(find.byKey(const Key('record-source-connected-device')));
    await tester.tap(find.byKey(const Key('record-source-import-audio')));
    expect(deviceSelected, isTrue);
    expect(importSelected, isTrue);
  });

  testWidgets('record options offer device pairing when nothing is connected', (tester) async {
    var devicePairingSelected = false;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: RecordOptionsSheet(
            onPickPhoneMic: () {},
            onPickPhoneCall: () {},
            onConnectDevice: () => devicePairingSelected = true,
            onImportAudio: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('record-source-connected-device')), findsNothing);
    expect(find.byKey(const Key('record-source-connect-device')), findsOneWidget);
    expect(find.byKey(const Key('record-source-import-audio')), findsOneWidget);

    await tester.tap(find.byKey(const Key('record-source-connect-device')));
    expect(devicePairingSelected, isTrue);
  });

  testWidgets('the home header always exposes device pairing before a device is connected', (tester) async {
    final homeProvider = HomeProvider();
    final deviceProvider = _DisconnectedDeviceProvider();
    addTearDown(homeProvider.dispose);
    addTearDown(deviceProvider.dispose);

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: MultiProvider(
          providers: [
            ChangeNotifierProvider<HomeProvider>.value(value: homeProvider),
            ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
          ],
          child: const Scaffold(body: BatteryInfoWidget()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Connect Device'), findsOneWidget);
  });
}
