import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/widgets/widget_state.dart';

void main() {
  test('state encodes the native widget keys', () {
    const state = WidgetState(
      recording: true,
      continuous: true,
      sourceKind: 'ble',
      source: 'Omi CV1',
      startedAt: 1234,
      transcriptLines: ['one', 'two'],
      transcriptState: 'Transcribing',
      deviceName: 'Casa',
      deviceBattery: 74,
      deviceConnected: true,
      targetDeviceId: 'AA:BB',
      targetAddress: 'AA:BB',
      targetRequiresBond: true,
      labelOneOff: 'Puntual',
      labelContinuous: 'Continua',
      labelStop: 'Atura',
      labelConnect: 'Connecta',
    );

    final json = state.toJson();

    expect(json['recording'], isTrue);
    expect(json['continuous'], isTrue);
    expect(json['source_kind'], 'ble');
    expect(json['started_at'], 1234);
    expect(json['transcript_lines'], ['one', 'two']);
    expect(json['device_battery'], 74);
    expect(json['target_address'], 'AA:BB');
    expect(json['label_one_off'], 'Puntual');
    expect(state.encode(), contains('"recording":true'));
  });

  test('defaults describe an idle widget', () {
    const state = WidgetState();

    expect(state.recording, isFalse);
    expect(state.transcriptLines, isEmpty);
    expect(state.deviceBattery, -1);
  });
}
