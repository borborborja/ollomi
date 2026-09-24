import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/capture/capture_status_view.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/widgets/widget_bridge.dart';
import 'package:omi/services/widgets/widget_state.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Keeps the Android home-screen widgets in sync with the app and executes the
/// actions a widget tap left behind.
///
/// The widgets can start/stop capture natively with the app closed; this
/// coordinator only pushes the localized state and handles the actions that
/// arrived by opening the app.
class WidgetCoordinator {
  WidgetCoordinator(this._bridge);

  final WidgetBridge _bridge;
  BuildContext? _context;
  CaptureProvider? _capture;
  DeviceProvider? _device;
  VoidCallback? _captureListener;
  VoidCallback? _deviceListener;
  Timer? _debounce;
  bool _attached = false;

  Future<void> attach(BuildContext context) async {
    if (_attached) return;
    _attached = true;
    _context = context;
    _capture = context.read<CaptureProvider>();
    _device = context.read<DeviceProvider>();

    // Any app start resumes native capture: the widget's stop pause must not
    // outlive the user opening Ollomi.
    await SharedPreferencesUtil().saveBool('widgetCapturePaused', false);

    _captureListener = () => _schedulePush();
    _deviceListener = () => _schedulePush(immediate: true);
    _capture!.addListener(_captureListener!);
    _device!.addListener(_deviceListener!);

    _bridge.setActionHandler(_handleAction);
    final pending = await _bridge.consumePendingAction();
    if (pending != null) {
      await _handleAction(pending);
    }
    await _push();
  }

  void dispose() {
    if (_captureListener != null) _capture?.removeListener(_captureListener!);
    if (_deviceListener != null) _device?.removeListener(_deviceListener!);
    _debounce?.cancel();
    _debounce = null;
    _context = null;
    _capture = null;
    _device = null;
    _attached = false;
  }

  void _schedulePush({bool immediate = false}) {
    _debounce?.cancel();
    if (immediate) {
      unawaited(_push());
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 500), () => unawaited(_push()));
  }

  Future<void> _handleAction(String action) async {
    final context = _context;
    final capture = _capture;
    final deviceProvider = _device;
    if (context == null || !context.mounted || capture == null || deviceProvider == null) return;
    Logger.debug('WidgetCoordinator action: $action');
    await SharedPreferencesUtil().saveBool('widgetCapturePaused', false);

    switch (action) {
      case 'start_one_off':
        if (capture.isCaptureActive) break; // native already started it
        final device = deviceProvider.connectedDevice;
        if (device != null) {
          await capture.streamDeviceRecording(device: device);
        } else {
          await capture.streamRecording();
        }
        break;
      case 'start_continuous':
        if (capture.isCaptureActive && capture.continuousCaptureEnabled) break;
        await capture.startContinuousCapture(device: deviceProvider.connectedDevice);
        break;
      case 'stop':
        if (capture.continuousCaptureEnabled) {
          await capture.stopContinuousCapture();
        } else {
          await capture.stopCurrentCapture();
        }
        break;
      case 'connect_device':
        await deviceProvider.initiateConnection('Widget');
        break;
      case 'open_transcript':
        final navigatorContext = globalNavigatorKey.currentContext;
        if (navigatorContext != null && navigatorContext.mounted) {
          Navigator.of(navigatorContext).push(
            MaterialPageRoute(
              settings: const RouteSettings(name: '/capture/active'),
              builder: (_) => ConversationCapturingPage(topConversationId: capture.topConversationId),
            ),
          );
        }
        break;
    }
    await _push();
  }

  Future<void> _push() async {
    final context = _context;
    final capture = _capture;
    final deviceProvider = _device;
    if (context == null || !context.mounted || capture == null || deviceProvider == null) return;
    final state = capture.captureUiState;

    final lines = capture.segments
        .where((segment) => segment.text.trim().isNotEmpty)
        .map((segment) => segment.text.trim())
        .toList()
        .reversed
        .take(2)
        .toList()
        .reversed
        .toList();

    final target = _targetDevice(deviceProvider);
    final recording = capture.isCaptureActive;

    await _bridge.pushState(
      WidgetState(
        recording: recording,
        continuous: capture.continuousCaptureEnabled,
        sourceKind: capture.recordingDevice != null ? 'ble' : (recording ? 'phone' : ''),
        source: recording ? captureSourceLabel(context, state) : '',
        startedAt: recording ? _startedAtMillis(capture) : 0,
        transcriptLines: lines,
        transcriptState: _transcriptState(context, capture, state.stage),
        deviceName: DeviceUtils.displayName(deviceProvider.connectedDevice),
        deviceBattery: deviceProvider.batteryLevel,
        deviceConnected: deviceProvider.connectedDevice != null,
        targetDeviceId: target?.id ?? '',
        targetAddress: target?.id ?? '',
        targetRequiresBond: false,
        labelOneOff: context.l10n.recordingOnConnectOneOff,
        labelContinuous: context.l10n.continuousRecording,
        labelStop: context.l10n.stopRecording,
        labelConnect: context.l10n.connectNow,
        labelIdle: 'Ollomi',
      ),
    );
  }

  int _startedAtMillis(CaptureProvider capture) {
    final seconds = capture.offlineRecordingStartedAt;
    if (seconds != null) return seconds * 1000;
    // Live sessions expose their start through the session id; fall back to now
    // rather than showing a timer that never advances.
    return DateTime.now().millisecondsSinceEpoch;
  }

  String _transcriptState(BuildContext context, CaptureProvider capture, CaptureUiStage stage) {
    if (capture.isPhoneMicBatchRecording) return context.l10n.transcribeLaterTitle;
    switch (stage) {
      case CaptureUiStage.offline:
        return context.l10n.transcribeLaterTitle;
      case CaptureUiStage.transcriptionDelayed:
        return context.l10n.captureTranscriptionDelayed;
      case CaptureUiStage.transcriptionUnavailable:
      case CaptureUiStage.reconnecting:
        return context.l10n.captureTranscriptionUnavailableRecordingContinues;
      default:
        return '';
    }
  }

  BtDevice? _targetDevice(DeviceProvider provider) {
    final connected = provider.connectedDevice;
    if (connected != null) return connected;
    final paired = provider.pairedDevice;
    if (paired != null && paired.id.isNotEmpty) return paired;
    final preferences = SharedPreferencesUtil();
    for (final device in preferences.btDevices) {
      if (device.id.isEmpty) continue;
      if (preferences.deviceAutoConnectFor(device.id)) return device;
    }
    return null;
  }
}
