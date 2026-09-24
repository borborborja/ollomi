import 'dart:convert';

/// State pushed to the Android home-screen widgets.
///
/// Keys mirror the native [OllomiWidgetState] JSON. Everything user-visible is a
/// localized label so the widgets follow the app language.
class OllomiWidgetState {
  const OllomiWidgetState({
    this.recording = false,
    this.continuous = false,
    this.sourceKind = '',
    this.source = '',
    this.startedAt = 0,
    this.transcriptLines = const [],
    this.transcriptState = '',
    this.deviceName = '',
    this.deviceBattery = -1,
    this.deviceConnected = false,
    this.targetDeviceId = '',
    this.targetAddress = '',
    this.targetRequiresBond = false,
    this.labelOneOff = 'Quick recording',
    this.labelContinuous = 'Continuous',
    this.labelStop = 'Stop',
    this.labelConnect = 'Connect',
    this.labelIdle = 'Ollomi',
  });

  final bool recording;
  final bool continuous;
  final String sourceKind;
  final String source;
  final int startedAt;
  final List<String> transcriptLines;
  final String transcriptState;
  final String deviceName;
  final int deviceBattery;
  final bool deviceConnected;
  final String targetDeviceId;
  final String targetAddress;
  final bool targetRequiresBond;
  final String labelOneOff;
  final String labelContinuous;
  final String labelStop;
  final String labelConnect;
  final String labelIdle;

  Map<String, dynamic> toJson() => {
    'recording': recording,
    'continuous': continuous,
    'source_kind': sourceKind,
    'source': source,
    'started_at': startedAt,
    'transcript_lines': transcriptLines,
    'transcript_state': transcriptState,
    'device_name': deviceName,
    'device_battery': deviceBattery,
    'device_connected': deviceConnected,
    'target_device_id': targetDeviceId,
    'target_address': targetAddress,
    'target_requires_bond': targetRequiresBond,
    'label_one_off': labelOneOff,
    'label_continuous': labelContinuous,
    'label_stop': labelStop,
    'label_connect': labelConnect,
    'label_idle': labelIdle,
  };

  String encode() => jsonEncode(toJson());
}
