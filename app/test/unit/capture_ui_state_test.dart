import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/utils/enums.dart';

class _OfflineConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

class _SourceSwitchCaptureProvider extends CaptureProvider {
  final events = <String>[];

  @override
  Future<void> stopStreamRecording({String reason = 'user_stopped'}) async {
    events.add('stop_phone:$reason');
    updateRecordingState(RecordingState.stop);
  }

  @override
  Future<void> stopStreamDeviceRecording({bool cleanDevice = false}) async {
    events.add('stop_device:$cleanDevice');
    if (cleanDevice) updateRecordingDevice(null);
    updateRecordingState(RecordingState.stop);
  }

  @override
  Future<void> streamRecording() async {
    events.add('start_phone');
    updateRecordingState(RecordingState.record);
  }

  @override
  Future<void> streamDeviceRecording({BtDevice? device}) async {
    events.add('start_device:${device?.id}');
    updateRecordingDevice(device);
    updateRecordingState(RecordingState.deviceRecord);
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _OfflineConnectivityPlatform();
  });

  test('decodes CV1 service status and exposes truthful capture stages', () {
    final provider = CaptureProvider();
    addTearDown(provider.dispose);
    provider.updateRecordingDevice(
      BtDevice(
        id: 'cv1',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -42,
        modelNumber: 'Omi CV 1',
      ),
    );
    provider.updateRecordingState(RecordingState.deviceRecord);
    provider.onConnected();

    void receive(Map<String, dynamic> json) {
      provider.onMessageEventReceived(MessageEvent.fromJson({'type': 'service_status', ...json}));
    }

    receive({'status': 'ready', 'source': 'omi'});
    expect(provider.captureUiState.stage, CaptureUiStage.waitingForAudio);
    expect(provider.captureUiState.deviceName, 'Omi CV1');

    receive({'status': 'audio_received', 'source': 'omi', 'audio_level': 0.35});
    expect(provider.captureUiState.stage, CaptureUiStage.receivingAudio);
    expect(provider.captureUiState.audioLevel, 0.35);
    expect(provider.captureUiState.serverSource, 'omi');

    receive({'status': 'transcribing', 'source': 'omi'});
    expect(provider.captureUiState.stage, CaptureUiStage.transcribing);

    receive({'status': 'no_speech', 'source': 'omi'});
    expect(provider.captureUiState.stage, CaptureUiStage.noSpeech);

    receive({'status': 'transcription_delayed', 'source': 'omi'});
    expect(provider.captureUiState.stage, CaptureUiStage.transcriptionDelayed);

    receive({'status': 'live_stt_unavailable', 'source': 'omi', 'retryable': true});
    expect(provider.captureUiState.stage, CaptureUiStage.transcriptionUnavailable);

    provider.onClosed();
    expect(provider.captureUiState.stage, CaptureUiStage.reconnecting);
    provider.updateRecordingState(RecordingState.stop);
  });

  test('source switching always stops the active pipeline before starting the next', () async {
    final provider = _SourceSwitchCaptureProvider();
    addTearDown(provider.dispose);
    final device = BtDevice(id: 'cv1', name: 'Omi', type: DeviceType.omi, rssi: -42);

    provider.updateRecordingState(RecordingState.pause);
    await provider.switchCaptureSource(device: device);
    expect(provider.events, ['stop_phone:source_switched', 'start_device:cv1']);

    provider.events.clear();
    await provider.switchCaptureSource();
    expect(provider.events, ['stop_device:true', 'start_phone']);

    provider.events.clear();
    provider.updateRecordingState(RecordingState.systemAudioRecord);
    await provider.switchCaptureSource(device: device);
    expect(provider.events, ['stop_phone:source_switched', 'start_device:cv1']);
  });
}
