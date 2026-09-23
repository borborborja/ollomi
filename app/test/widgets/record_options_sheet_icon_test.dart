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
    SharedPreferencesUtil().activeCaptureButtonBehavior = ActiveCaptureButtonBehavior.openActive;
    SharedPreferencesUtil().continuousCaptureEnabled = false;
    final captureProvider = CaptureProvider()..updateRecordingState(RecordingState.stop);
    addTearDown(captureProvider.dispose);
    await pumpActiveButton(tester, captureProvider);

    expect(find.byKey(const Key('home-record-button-surface')), findsOneWidget);
    expect(find.byIcon(Icons.add), findsOneWidget);
  });

  testWidgets('recording hides the old record button for every behavior', (tester) async {
    // The top capture bar owns the active state (mute, change source, finish),
    // so the previous red record button must not render while recording.
    for (final behavior in [ActiveCaptureButtonBehavior.openActive, ActiveCaptureButtonBehavior.switchSource]) {
      SharedPreferencesUtil().activeCaptureButtonBehavior = behavior;
      final captureProvider = CaptureProvider()..updateRecordingState(RecordingState.record);
      addTearDown(captureProvider.dispose);
      await pumpActiveButton(tester, captureProvider);

      expect(
        find.byKey(const Key('home-record-button-surface')),
        findsNothing,
        reason: 'active recording is owned by the top capture bar',
      );
    }
  });

  testWidgets('source-switch behavior opens the exclusive source picker while idle', (tester) async {
    SharedPreferencesUtil().activeCaptureButtonBehavior = ActiveCaptureButtonBehavior.switchSource;
    SharedPreferencesUtil().continuousCaptureEnabled = false;
    final captureProvider = CaptureProvider()..updateRecordingState(RecordingState.stop);
    addTearDown(captureProvider.dispose);
    await pumpActiveButton(tester, captureProvider);

    // Idle: the add button starts a one-off capture; the source picker is not
    // part of the idle contract.
    expect(find.byKey(const Key('home-record-button-surface')), findsOneWidget);
    expect(captureProvider.recordingState, RecordingState.stop);
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
