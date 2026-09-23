import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/capture/capture_status_view.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Single recording control at the top of the home screen.
///
/// Idle: shows the continuous-recording switch (the one-off "+" record button
/// stays independently available).
/// Recording: shows the active source plus mute and change-device actions.
/// During a one-off recording the continuous switch is replaced by a finish
/// button, because continuous mode cannot be toggled while a one-off is live.
class HomeCaptureBar extends StatefulWidget {
  const HomeCaptureBar({super.key});

  @override
  State<HomeCaptureBar> createState() => _HomeCaptureBarState();
}

class _HomeCaptureBarState extends State<HomeCaptureBar> {
  // Phone live capture has no provider-level mute flag (the native mic stops and
  // restarts), so the bar tracks the toggle locally like the capturing page.
  bool _phoneMuted = false;

  void _openActiveCapture(BuildContext context) {
    final captureProvider = context.read<CaptureProvider>();
    Navigator.push(
      context,
      MaterialPageRoute(
        settings: const RouteSettings(name: '/capture/active'),
        builder: (_) => ConversationCapturingPage(topConversationId: captureProvider.topConversationId),
      ),
    );
  }

  Future<void> _enableContinuous(BuildContext context) async {
    HapticFeedback.lightImpact();
    final captureProvider = context.read<CaptureProvider>();
    if (captureProvider.isCaptureActive) {
      SharedPreferencesUtil().continuousCaptureEnabled = true;
      captureProvider.notifyListeners();
      return;
    }
    await _showSourcePicker(context);
  }

  Future<void> _showSourcePicker(BuildContext context) async {
    final captureProvider = context.read<CaptureProvider>();
    final connectedDevice = context.read<DeviceProvider>().connectedDevice;
    final continuous = SharedPreferencesUtil().continuousCaptureEnabled;
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _CaptureSourceSheet(
        connectedDevice: connectedDevice,
        onPickPhone: () {
          Navigator.pop(sheetContext);
          if (continuous) {
            captureProvider.startContinuousCapture();
          } else {
            captureProvider.switchCaptureSource();
          }
        },
        onPickDevice: connectedDevice == null
            ? null
            : () {
                Navigator.pop(sheetContext);
                if (continuous) {
                  captureProvider.startContinuousCapture(device: connectedDevice);
                } else {
                  captureProvider.switchCaptureSource(device: connectedDevice);
                }
              },
        onConnectDevice: connectedDevice == null
            ? () {
                Navigator.pop(sheetContext);
                routeToPage(context, const ConnectDevicePage());
              }
            : null,
      ),
    );
  }

  bool _isMuted(CaptureProvider provider) {
    if (provider.recordingDevice != null) return provider.isPaused;
    if (provider.isPhoneMicBatchRecording) return provider.offlineMuted;
    return _phoneMuted;
  }

  Future<void> _toggleMute(BuildContext context) async {
    final provider = context.read<CaptureProvider>();
    HapticFeedback.mediumImpact();
    if (provider.recordingDevice != null) {
      if (provider.isPaused) {
        await provider.resumeDeviceRecording();
      } else {
        await provider.pauseDeviceRecording();
      }
      return;
    }
    if (provider.isPhoneMicBatchRecording) {
      provider.toggleOfflineMute();
      return;
    }
    if (_phoneMuted) {
      await provider.streamRecording();
    } else {
      await provider.stopStreamRecording();
    }
    if (mounted) setState(() => _phoneMuted = !_phoneMuted);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, captureProvider, deviceProvider, _) {
        final continuous = SharedPreferencesUtil().continuousCaptureEnabled;
        final isRecording = captureProvider.isCaptureActive;
        final isInitialising = captureProvider.recordingState == RecordingState.initialising;
        final state = captureProvider.captureUiState;
        final source = isRecording ? captureSourceLabel(context, state) : null;
        final muted = isRecording && _isMuted(captureProvider);

        return Container(
          margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          padding: const EdgeInsets.only(left: 14, right: 6, top: 6, bottom: 6),
          decoration: BoxDecoration(
            color: const Color(0xFF1C1C1E),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isRecording || continuous ? const Color(0xFFFE5D50).withValues(alpha: 0.5) : const Color(0xFF2A2A2E),
            ),
          ),
          child: Row(
            children: [
              GestureDetector(
                onTap: isRecording ? () => _openActiveCapture(context) : null,
                behavior: HitTestBehavior.opaque,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 9,
                      height: 9,
                      decoration: BoxDecoration(
                        color: isRecording ? const Color(0xFFFE5D50) : const Color(0xFF3C3C43),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      isRecording ? context.l10n.recording : context.l10n.continuousRecording,
                      style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                    ),
                    if (source != null) ...[
                      const SizedBox(width: 6),
                      Text('· $source', style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13)),
                    ],
                  ],
                ),
              ),
              const Spacer(),
              if (isRecording) ...[
                _BarAction(
                  buttonKey: const Key('capture_bar_mute'),
                  icon: muted ? FontAwesomeIcons.microphoneSlash : FontAwesomeIcons.microphone,
                  tooltip: muted ? context.l10n.unmute : context.l10n.mute,
                  active: muted,
                  onTap: () => _toggleMute(context),
                ),
                _BarAction(
                  buttonKey: const Key('capture_bar_change_source'),
                  icon: FontAwesomeIcons.rightLeft,
                  tooltip: context.l10n.activeCaptureButtonSwitchSource,
                  onTap: () => _showSourcePicker(context),
                ),
              ],
              if (isRecording && !continuous)
                _BarAction(
                  buttonKey: const Key('capture_bar_finish'),
                  icon: FontAwesomeIcons.stop,
                  tooltip: context.l10n.stopRecording,
                  danger: true,
                  onTap: () {
                    HapticFeedback.mediumImpact();
                    captureProvider.stopCurrentCapture();
                  },
                )
              else if (!isInitialising)
                Padding(
                  padding: const EdgeInsets.only(left: 2),
                  child: Switch(
                    key: const Key('continuous_capture_switch'),
                    value: continuous,
                    activeThumbColor: Colors.white,
                    activeTrackColor: const Color(0xFFFE5D50),
                    onChanged: (value) {
                      if (value) {
                        _enableContinuous(context);
                      } else {
                        HapticFeedback.lightImpact();
                        captureProvider.stopContinuousCapture();
                      }
                    },
                  ),
                )
              else
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 14),
                  child: SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _BarAction extends StatelessWidget {
  const _BarAction({
    required this.buttonKey,
    required this.icon,
    required this.tooltip,
    required this.onTap,
    this.active = false,
    this.danger = false,
  });

  final Key buttonKey;
  final FaIconData icon;
  final String tooltip;
  final VoidCallback onTap;
  final bool active;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final color = danger
        ? const Color(0xFFFE5D50)
        : active
            ? const Color(0xFFFE5D50)
            : Colors.white;
    return Tooltip(
      message: tooltip,
      child: GestureDetector(
        key: buttonKey,
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Container(
          width: 40,
          height: 40,
          margin: const EdgeInsets.only(right: 2),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: active ? color.withValues(alpha: 0.15) : Colors.transparent,
            shape: BoxShape.circle,
          ),
          child: FaIcon(icon, color: color, size: 17),
        ),
      ),
    );
  }
}

class _CaptureSourceSheet extends StatelessWidget {
  const _CaptureSourceSheet({
    required this.connectedDevice,
    required this.onPickPhone,
    this.onPickDevice,
    this.onConnectDevice,
  });

  final BtDevice? connectedDevice;
  final VoidCallback onPickPhone;
  final VoidCallback? onPickDevice;
  final VoidCallback? onConnectDevice;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  margin: const EdgeInsets.only(bottom: 16),
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(color: const Color(0xFF3C3C43), borderRadius: BorderRadius.circular(2)),
                ),
              ),
              Text(
                context.l10n.continuousRecordingSource,
                style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              if (connectedDevice != null)
                _SourceOption(
                  key: const Key('continuous_source_device'),
                  icon: FontAwesomeIcons.bluetooth,
                  title: DeviceUtils.displayName(connectedDevice),
                  recommended: true,
                  onTap: onPickDevice,
                ),
              _SourceOption(
                key: const Key('continuous_source_phone'),
                icon: FontAwesomeIcons.mobileScreen,
                title: context.l10n.memoryThisDevice,
                recommended: false,
                onTap: onPickPhone,
              ),
              if (connectedDevice == null) ...[
                const SizedBox(height: 4),
                _SourceOption(
                  key: const Key('continuous_source_connect_device'),
                  icon: FontAwesomeIcons.link,
                  title: context.l10n.connectDevice,
                  recommended: false,
                  onTap: onConnectDevice,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SourceOption extends StatelessWidget {
  const _SourceOption({
    super.key,
    required this.icon,
    required this.title,
    required this.recommended,
    required this.onTap,
  });

  final FaIconData icon;
  final String title;
  final bool recommended;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(
          children: [
            SizedBox(width: 24, height: 24, child: FaIcon(icon, color: const Color(0xFF8E8E93), size: 18)),
            const SizedBox(width: 14),
            Expanded(child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 16))),
            if (recommended)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: const Color(0xFF4CAF50).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  context.l10n.recommended,
                  style: const TextStyle(color: Color(0xFF4CAF50), fontSize: 11, fontWeight: FontWeight.w600),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
