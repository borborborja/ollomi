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
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Top-of-home control for continuous recording.
///
/// Off: recording is one-off and started from the "+" record button.
/// On: a single long-running capture keeps recording in the background (phone
/// or a paired device) and shows a compact active card that opens the live
/// transcription. Conversations are separated by the "new conversation"
/// action or the configured silence timeout.
class ContinuousCaptureBar extends StatelessWidget {
  const ContinuousCaptureBar({super.key});

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

  Future<void> _enable(BuildContext context) async {
    HapticFeedback.lightImpact();
    final captureProvider = context.read<CaptureProvider>();
    final deviceProvider = context.read<DeviceProvider>();
    if (captureProvider.isCaptureActive) {
      SharedPreferencesUtil().continuousCaptureEnabled = true;
      captureProvider.notifyListeners();
      return;
    }
    final connectedDevice = deviceProvider.connectedDevice;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _ContinuousSourceSheet(
        connectedDevice: connectedDevice,
        onPickPhone: () {
          Navigator.pop(sheetContext);
          captureProvider.startContinuousCapture();
        },
        onPickDevice: connectedDevice == null
            ? null
            : () {
                Navigator.pop(sheetContext);
                captureProvider.startContinuousCapture(device: connectedDevice);
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

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, captureProvider, deviceProvider, _) {
        final enabled = SharedPreferencesUtil().continuousCaptureEnabled;
        final isRecording = captureProvider.isCaptureActive;
        final state = captureProvider.captureUiState;
        final source = isRecording ? captureSourceLabel(context, state) : null;

        return Container(
          margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: const Color(0xFF1C1C1E),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: enabled ? const Color(0xFFFE5D50).withValues(alpha: 0.5) : const Color(0xFF2A2A2E),
            ),
          ),
          child: Row(
            children: [
              GestureDetector(
                onTap: isRecording ? () => _openActiveCapture(context) : null,
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
                      Text(
                        '· $source',
                        style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13),
                      ),
                    ],
                  ],
                ),
              ),
              const Spacer(),
              if (isRecording)
                GestureDetector(
                  key: const Key('continuous_capture_open'),
                  onTap: () => _openActiveCapture(context),
                  child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 6),
                    child: FaIcon(FontAwesomeIcons.upRightAndDownLeftFromCenter, size: 15, color: Colors.white70),
                  ),
                ),
              Switch(
                key: const Key('continuous_capture_switch'),
                value: enabled,
                activeThumbColor: Colors.white,
                activeTrackColor: const Color(0xFFFE5D50),
                onChanged: (value) {
                  if (value) {
                    _enable(context);
                  } else {
                    HapticFeedback.lightImpact();
                    captureProvider.stopContinuousCapture();
                  }
                },
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ContinuousSourceSheet extends StatelessWidget {
  const _ContinuousSourceSheet({
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
                  subtitle: null,
                  recommended: true,
                  onTap: onPickDevice,
                ),
              _SourceOption(
                key: const Key('continuous_source_phone'),
                icon: FontAwesomeIcons.mobileScreen,
                title: context.l10n.memoryThisDevice,
                subtitle: null,
                recommended: false,
                onTap: onPickPhone,
              ),
              if (connectedDevice == null) ...[
                const SizedBox(height: 4),
                _SourceOption(
                  key: const Key('continuous_source_connect_device'),
                  icon: FontAwesomeIcons.link,
                  title: context.l10n.connectDevice,
                  subtitle: null,
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
    required this.subtitle,
    required this.recommended,
    required this.onTap,
  });

  final FaIconData icon;
  final String title;
  final String? subtitle;
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
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(color: Colors.white, fontSize: 16)),
                  if (subtitle != null)
                    Text(
                      subtitle!,
                      style: const TextStyle(color: Color(0xFF4CAF50), fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                ],
              ),
            ),
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
