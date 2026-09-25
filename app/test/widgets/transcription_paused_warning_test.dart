import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/enums.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get connectedDevice => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubConnectivityProvider extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubPhoneCallProvider extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized or platform channels unavailable
    }
  });

  Future<void> pumpCaptureWidget(WidgetTester tester, CaptureProvider captureProvider) async {
    final deviceProvider = _StubDeviceProvider();
    final connectivityProvider = _StubConnectivityProvider();
    final phoneCallProvider = _StubPhoneCallProvider();
    addTearDown(deviceProvider.dispose);
    addTearDown(connectivityProvider.dispose);
    addTearDown(phoneCallProvider.dispose);

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
          body: MultiProvider(
            providers: [
              ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
              ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivityProvider),
              ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
              ChangeNotifierProvider<PhoneCallProvider>.value(value: phoneCallProvider),
            ],
            child: const ConversationCaptureWidget(),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  // These cases were written against the old simplified status line, which
  // printed a bare "Listening" whenever a capture was active. `4f99aa19` made
  // the card explicit: it now renders `captureStageLabel(context, state)` plus
  // the source, so a stage that used to read "Listening" reads
  // "Listening for audio..."/"Preparing audio capture"/"Still recording —
  // reconnecting..." depending on the real pipeline state. The guards below
  // keep each test's original intent — a recording session never claims a
  // healthy capture while the socket is down, and pause always overrides it —
  // against the labels the widget actually renders.
  group('simplified status indicators (#6672)', () {
    testWidgets('shows terminal live STT failure until the backend is ready again', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.record);

      await pumpCaptureWidget(tester, captureProvider);

      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(
          status: 'stt_failed',
          outcome: 'upstream_error',
          provider: 'deepgram',
          retryable: true,
          reason: 'send_failed',
        ),
      );
      await tester.pump();

      expect(captureProvider.recordingState, RecordingState.record);
      expect(captureProvider.terminalTranscriptionFailure?.status, 'stt_failed');
      final context = tester.element(find.byType(ConversationCaptureWidget));
      expect(
        find.textContaining(AppLocalizations.of(context).captureTranscriptionUnavailableRecordingContinues),
        findsWidgets,
      );

      captureProvider.onMessageEventReceived(MessageServiceStatusEvent(status: 'ready'));
      await tester.pump();

      expect(
        find.textContaining(AppLocalizations.of(context).captureTranscriptionUnavailableRecordingContinues),
        findsNothing,
      );
    });

    testWidgets('shows Paused for non-call audio interruption (#4706)', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      // recordingState=interrupted without micInterrupted → isCallActive is false
      // (other-app audio / silent stall path, not an active phone call).
      captureProvider.updateRecordingState(RecordingState.interrupted);
      expect(captureProvider.isCallActive, isFalse);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final pausedText = AppLocalizations.of(context).paused;

      expect(find.textContaining(pausedText), findsWidgets);
      // Phone-mic paused affordance: orange status dot + play (resume) control.
      expect(
        find.byWidgetPredicate((w) {
          if (w is! Container) return false;
          final d = w.decoration;
          return d is BoxDecoration &&
              d.color == const Color(0xFFFF9500) &&
              d.shape == BoxShape.circle &&
              w.constraints?.maxWidth == 6;
        }),
        findsOneWidget,
      );
      expect(
        find.byWidgetPredicate((w) => w is FaIcon && w.icon?.codePoint == FontAwesomeIcons.play.codePoint),
        findsOneWidget,
      );
    });

    testWidgets('shows Listening during phone mic recording when transcription is down', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.record);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      // The socket never connected in this harness, so the truthful stage is the
      // reconnect copy rather than a bare "Listening".
      final reconnectingText = AppLocalizations.of(context).transcriptionPausedReconnecting;

      expect(find.textContaining(reconnectingText), findsWidgets);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('shows Listening during initialising state', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.initialising);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final preparingText = AppLocalizations.of(context).preparingAudioCapture;

      expect(find.textContaining(preparingText), findsWidgets);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('shows Listening during device recording when transcription is down', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      // Set up a fake recording device to exercise the device recording path
      captureProvider.updateRecordingDevice(
        BtDevice(id: 'test-device', name: 'Test Omi', type: DeviceType.omi, rssi: -50),
      );
      captureProvider.updateRecordingState(RecordingState.deviceRecord);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final reconnectingText = AppLocalizations.of(context).transcriptionPausedReconnecting;

      expect(find.textContaining(reconnectingText), findsWidgets);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('paused state overrides Listening during device recording', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingDevice(
        BtDevice(id: 'test-device', name: 'Test Omi', type: DeviceType.omi, rssi: -50),
      );
      captureProvider.updateRecordingState(RecordingState.deviceRecord);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final reconnectingText = AppLocalizations.of(context).transcriptionPausedReconnecting;
      final mutedText = AppLocalizations.of(context).muted;

      // Initially the device capture is live; the socket is down in this harness.
      expect(find.textContaining(reconnectingText), findsWidgets);

      // Simulate device pause: set isPaused and change to pause state
      captureProvider.updateRecordingState(RecordingState.pause);
      // isPaused is set via pauseDeviceRecording which needs BLE — set it directly
      // by triggering the internal pause flow
      try {
        await captureProvider.pauseDeviceRecording();
      } catch (_) {
        // BLE operations fail in test — but isPaused flag is set before the throw
      }
      await tester.pump();

      // Muted/Paused should override Listening for device recording
      expect(find.textContaining(mutedText), findsWidgets);
    });
  });
}
