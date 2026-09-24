import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/capture/capture_status_view.dart';
import 'package:omi/pages/capture/widgets/capture_level_meter.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/local_segment_store.dart';

class _OfflineConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _OfflineConnectivityPlatform();
  });

  test('pcm16 level measures silence, half scale and full scale', () {
    expect(CaptureController.pcm16Level(List<int>.filled(320, 0)), 0);

    final halfScale = <int>[];
    final fullScale = <int>[];
    for (var i = 0; i < 160; i++) {
      halfScale
        ..add(0x00)
        ..add(0x40); // 16384
      fullScale
        ..add(0xFF)
        ..add(0x7F); // 32767
    }
    expect(CaptureController.pcm16Level(halfScale), closeTo(0.5, 0.01));
    expect(CaptureController.pcm16Level(fullScale), closeTo(0.999, 0.01));
  });

  test('the perceptual curve lifts quiet speech', () {
    expect(CaptureController.normalizeAudioLevel(0.0), 0);
    expect(CaptureController.normalizeAudioLevel(0.25), closeTo(0.5, 0.001));
    expect(CaptureController.normalizeAudioLevel(1.0), 1);
  });

  test('the meter rises instantly and releases to zero', () {
    fakeAsync((async) {
      final provider = CaptureProvider(localSegmentStore: LocalSegmentStore.disabled());

      provider.pushAudioLevelForTesting(0.25);
      expect(provider.displayAudioLevelForTesting, closeTo(0.5, 0.001));

      async.elapse(const Duration(seconds: 3));
      expect(provider.displayAudioLevelForTesting, 0.0);
      provider.dispose();
    });
  });

  testWidgets('the meter follows the level with three animated bars', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: CaptureLevelMeter(level: 0))),
    );
    final bars = find.descendant(of: find.byType(CaptureLevelMeter), matching: find.byType(Container));
    expect(bars, findsNWidgets(3));
    expect(tester.getSize(bars.at(1)).height, closeTo(20 * 0.2, 0.1));

    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: CaptureLevelMeter(level: 1))),
    );
    await tester.pumpAndSettle();
    expect(tester.getSize(bars.at(1)).height, closeTo(20, 0.1));
  });

  testWidgets('the capture status view renders the meter', (tester) async {
    const state = CaptureUiState(
      stage: CaptureUiStage.receivingAudio,
      source: CaptureUiSource.phone,
      audioLevel: 0.6,
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(body: CaptureStatusView(state: state)),
      ),
    );
    expect(find.byKey(const Key('capture-server-audio-level')), findsOneWidget);
    expect(find.byType(CaptureLevelMeter), findsOneWidget);
  });
}
