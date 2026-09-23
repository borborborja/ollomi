import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/capture/capture_status_view.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/pages/settings/selfhost_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/omi_confirm_dialog.dart';

class BatteryInfoWidget extends StatefulWidget {
  const BatteryInfoWidget({super.key});

  @override
  State<BatteryInfoWidget> createState() => _BatteryInfoWidgetState();
}

class _BatteryInfoWidgetState extends State<BatteryInfoWidget> {
  @override
  Widget build(BuildContext context) {
    return Selector<HomeProvider, bool>(
      selector: (context, state) => state.selectedIndex == 0,
      builder: (context, isMemoriesPage, child) {
        // Use Selector to only rebuild when battery level, connected device, or connecting state changes
        // This reduces battery drain by avoiding unnecessary rebuilds during other provider updates
        return Selector<DeviceProvider, (int, BtDevice?, BtDevice?, bool, bool)>(
          selector: (_, provider) => (
            provider.batteryLevel,
            provider.connectedDevice,
            provider.pairedDevice,
            provider.isConnecting,
            provider.isCharging,
          ),
          builder: (context, data, child) {
            final (batteryLevel, connectedDevice, pairedDevice, isConnecting, isCharging) = data;
            if (connectedDevice != null) {
              final batteryPill = GestureDetector(
                onTap: () {
                  routeToPage(context, const ConnectedDevice());
                  PlatformManager.instance.analytics.batteryIndicatorClicked();
                },
                child: Container(
                  height: 36,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                  decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(18)),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Add device icon
                      SizedBox(
                        width: 16,
                        height: 16,
                        child: Image.asset(
                          DeviceUtils.getDeviceImagePath(
                            deviceType: connectedDevice.type,
                            modelNumber: connectedDevice.modelNumber,
                            deviceName: connectedDevice.name,
                          ),
                          fit: BoxFit.contain,
                        ),
                      ),
                      // Only show battery indicator and percentage when battery level is valid (> 0)
                      if (batteryLevel > 0) ...[
                        const SizedBox(width: 6.0),
                        if (isCharging)
                          const Icon(Icons.bolt, color: Color.fromARGB(255, 0, 255, 8), size: 14)
                        else
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: batteryLevel > 75
                                  ? const Color.fromARGB(255, 0, 255, 8)
                                  : batteryLevel > 20
                                      ? Colors.yellow.shade700
                                      : Colors.red,
                              shape: BoxShape.circle,
                            ),
                          ),
                        const SizedBox(width: 4.0),
                        Text(
                          '$batteryLevel%',
                          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                        ),
                      ],
                    ],
                  ),
                ),
              );
              if (!isMemoriesPage) return batteryPill;
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  batteryPill,
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: () {
                      HapticFeedback.lightImpact();
                      Navigator.push(context, MaterialPageRoute(builder: (_) => const PhoneCallsPage()));
                    },
                    child: Container(
                      height: 36,
                      width: 36,
                      decoration: BoxDecoration(
                        color: const Color(0xFF1F1F25),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: const Icon(Icons.phone_in_talk_rounded, color: Colors.white, size: 16),
                    ),
                  ),
                ],
              );
            } else if (pairedDevice != null && pairedDevice.id.isNotEmpty) {
              // Device is paired but disconnected
              return GestureDetector(
                onTap: () async {
                  await routeToPage(context, const ConnectedDevice());
                },
                child: Container(
                  height: 36,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                  decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(18)),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Device icon with slash line
                      SizedBox(
                        width: 16,
                        height: 16,
                        child: Stack(
                          children: [
                            Image.asset(DeviceUtils.getDeviceImageFromBtDevice(pairedDevice), fit: BoxFit.contain),
                            // Slash line across the image
                            Positioned.fill(child: CustomPaint(painter: SlashLinePainter())),
                          ],
                        ),
                      ),
                      const SizedBox(width: 6.0),
                      Text(
                        context.l10n.disconnected,
                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white70, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              );
            } else {
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  GestureDetector(
                    onTap: () async {
                      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
                        routeToPage(context, const ConnectDevicePage());
                        PlatformManager.instance.analytics.connectFriendClicked();
                      } else {
                        await routeToPage(context, const ConnectedDevice());
                      }
                    },
                    child: Container(
                      height: 36,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1F1F25),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Image.asset(Assets.images.logoTransparent.path, width: 16, height: 16),
                          const SizedBox(width: 6),
                          isConnecting
                              ? Text(
                                  context.l10n.searching,
                                  style: Theme.of(
                                    context,
                                  ).textTheme.bodyMedium!.copyWith(color: Colors.white, fontSize: 12),
                                )
                              : Text(
                                  context.l10n.connectDevice,
                                  style: const TextStyle(color: Colors.white, fontSize: 12),
                                ),
                        ],
                      ),
                    ),
                  ),
                ],
              );
            }
          },
        );
      },
    );
  }
}

/// Circular phone-mic record button shown to the right of the home chat bar.
/// Tap starts/stops recording; long-press opens the record options sheet.
class HomeRecordButton extends StatefulWidget {
  const HomeRecordButton({super.key});

  @override
  State<HomeRecordButton> createState() => _HomeRecordButtonState();
}

class _HomeRecordButtonState extends State<HomeRecordButton> {
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

  Future<void> _confirmSourceSwitch(BuildContext context, {BtDevice? device}) async {
    final captureProvider = context.read<CaptureProvider>();
    final sameSource = device == null
        ? captureProvider.isPhoneCaptureActive
        : captureProvider.recordingDevice?.id == device.id &&
            (captureProvider.recordingState == RecordingState.deviceRecord ||
                captureProvider.recordingState == RecordingState.pause);
    if (sameSource) {
      _openActiveCapture(context);
      return;
    }

    final target = DeviceUtils.displayName(device, fallback: context.l10n.memoryThisDevice);
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.activeCaptureButtonSwitchSource,
      message: '${context.l10n.stopRecordingConfirmation}\n\n${context.l10n.audioInputSetTo(target)}',
      confirmLabel: context.l10n.switchAndRestart,
      confirmColor: const Color(0xFFFE5D50),
    );
    if (confirmed != true || !context.mounted) return;
    await captureProvider.switchCaptureSource(device: device);
    if (context.mounted && captureProvider.isCaptureActive) _openActiveCapture(context);
  }

  void _showActiveSourcePicker(BuildContext context) {
    HapticFeedback.lightImpact();
    final connectedDevice = context.read<DeviceProvider>().connectedDevice;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _ActiveCaptureSourceSheet(
        connectedDevice: connectedDevice,
        onPickPhone: () {
          Navigator.pop(sheetContext);
          _confirmSourceSwitch(context);
        },
        onPickDevice: connectedDevice == null
            ? null
            : () {
                Navigator.pop(sheetContext);
                _confirmSourceSwitch(context, device: connectedDevice);
              },
      ),
    );
  }

  void _showRecordOptions(BuildContext context) {
    HapticFeedback.lightImpact();
    final connectedDevice = context.read<DeviceProvider>().connectedDevice;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) => RecordOptionsSheet(
        onPickPhoneMic: () {
          Navigator.pop(sheetContext);
          _startRecording(context);
        },
        onPickPhoneCall: () {
          Navigator.pop(sheetContext);
          if (!context.mounted) return;
          Navigator.push(context, MaterialPageRoute(builder: (_) => const PhoneCallsPage()));
        },
        connectedDeviceName: DeviceUtils.displayName(connectedDevice),
        onPickConnectedDevice: connectedDevice == null
            ? null
            : () {
                Navigator.pop(sheetContext);
                _startDeviceRecording(context, connectedDevice);
              },
        onConnectDevice: connectedDevice == null
            ? () {
                Navigator.pop(sheetContext);
                if (!context.mounted) return;
                routeToPage(context, const ConnectDevicePage());
              }
            : null,
        onImportAudio: () {
          Navigator.pop(sheetContext);
          if (!context.mounted) return;
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const ImportAudioPage(pickOnOpen: true)),
          );
        },
      ),
    );
  }

  Future<void> _startDeviceRecording(BuildContext context, BtDevice device) async {
    HapticFeedback.mediumImpact();
    final captureProvider = context.read<CaptureProvider>();
    final sameDevice = captureProvider.recordingDevice?.id == device.id;

    if (sameDevice && captureProvider.recordingState == RecordingState.pause) {
      await captureProvider.resumeDeviceRecording();
    } else if (!sameDevice || captureProvider.recordingState != RecordingState.deviceRecord) {
      await captureProvider.streamDeviceRecording(device: device);
    }

    if (!context.mounted || captureProvider.recordingState != RecordingState.deviceRecord) return;
    if (SharedPreferencesUtil().batchModeEnabled) {
      AppSnackbar.showSnackbar(context.l10n.recording);
      return;
    }
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ConversationCapturingPage(topConversationId: captureProvider.topConversationId),
      ),
    );
  }

  Future<void> _startRecording(BuildContext context) async {
    HapticFeedback.mediumImpact();
    final captureProvider = context.read<CaptureProvider>();
    if (captureProvider.recordingState == RecordingState.initialising) return;
    if (captureProvider.recordingState == RecordingState.record) {
      // Batch reports RecordingState.record too, but has no in-progress conversation
      // to force-process — stopStreamRecording finalizes the local .bin on its own.
      final wasBatch = captureProvider.isPhoneMicBatchRecording;
      await captureProvider.stopStreamRecording();
      if (!wasBatch) captureProvider.forceProcessingCurrentConversation();
      PlatformManager.instance.analytics.phoneMicRecordingStopped();
      return;
    }
    await captureProvider.streamRecording();
    PlatformManager.instance.analytics.phoneMicRecordingStarted();
    // Phone-mic Transcribe Later (batch) has no live transcript — its surface is the
    // conversations-list batch card, so skip the capturing page (same as BLE batch).
    if (captureProvider.isPhoneMicBatchRecording) {
      if (SharedPreferencesUtil().phoneBatchAuto && context.mounted) {
        AppSnackbar.showSnackbar(context.l10n.phoneMicOfflineFallbackMessage);
      }
      return;
    }
    if (context.mounted) {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => ConversationCapturingPage(topConversationId: captureProvider.topConversationId),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CaptureProvider>(
      builder: (context, captureProvider, _) {
        final isRecording = captureProvider.isCaptureActive;
        final isInitialising = captureProvider.recordingState == RecordingState.initialising;
        final behavior = SharedPreferencesUtil().activeCaptureButtonBehavior;
        if (isRecording && behavior == ActiveCaptureButtonBehavior.hide) {
          return const SizedBox.shrink();
        }
        // In continuous mode the top switch owns the capture lifecycle, so the
        // "+" record options button is not shown; the active card replaces it.
        if (SharedPreferencesUtil().continuousCaptureEnabled && !isRecording) {
          return const SizedBox.shrink();
        }
        final captureState = captureProvider.captureUiState;
        final source = captureSourceLabel(context, captureState);
        final activeIcon =
            behavior == ActiveCaptureButtonBehavior.switchSource ? Icons.swap_horiz_rounded : Icons.graphic_eq_rounded;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            if (!isRecording) {
              _startRecording(context);
            } else if (behavior == ActiveCaptureButtonBehavior.switchSource) {
              _showActiveSourcePicker(context);
            } else {
              _openActiveCapture(context);
            }
          },
          onLongPress: isRecording || isInitialising ? null : () => _showRecordOptions(context),
          child: AnimatedContainer(
            key: const Key('home-record-button-surface'),
            duration: const Duration(milliseconds: 200),
            width: isRecording ? 76 : 62,
            height: 62,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: isRecording ? const Color(0xFFB3261E) : const Color(0xFF35343B),
              borderRadius: BorderRadius.circular(31),
            ),
            child: isRecording
                ? Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(activeIcon, size: 21, color: Colors.white),
                      const SizedBox(height: 2),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 6),
                        child: Text(
                          source,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  )
                : isInitialising
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.add, size: 28, color: Colors.white),
          ),
        );
      },
    );
  }
}

class SlashLinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.red
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    // Position the cross at the bottom right
    final crossSize = size.width * 0.2; // Size of the cross
    final centerX = size.width - crossSize / 2 - 2; // Bottom right positioning
    final centerY = size.height - crossSize / 2 - 2;
    final halfCrossSize = crossSize / 2;

    // Draw the X (cross) - two diagonal lines
    canvas.drawLine(
      Offset(centerX - halfCrossSize, centerY - halfCrossSize),
      Offset(centerX + halfCrossSize, centerY + halfCrossSize),
      paint,
    );

    canvas.drawLine(
      Offset(centerX + halfCrossSize, centerY - halfCrossSize),
      Offset(centerX - halfCrossSize, centerY + halfCrossSize),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _ActiveCaptureSourceSheet extends StatelessWidget {
  const _ActiveCaptureSourceSheet({
    required this.connectedDevice,
    required this.onPickPhone,
    required this.onPickDevice,
  });

  final BtDevice? connectedDevice;
  final VoidCallback onPickPhone;
  final VoidCallback? onPickDevice;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(16, 12, 16, MediaQuery.of(context).padding.bottom + 16),
      decoration: const BoxDecoration(
        color: Color(0xFF1F1F25),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 18),
          Text(
            context.l10n.activeCaptureButtonSwitchSource,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
          _RecordOption(
            key: const Key('active-capture-source-phone'),
            icon: FontAwesomeIcons.microphone,
            title: context.l10n.memoryThisDevice,
            subtitle: context.l10n.recordWithPhoneMicSubtitle,
            onTap: onPickPhone,
          ),
          if (connectedDevice != null && onPickDevice != null) ...[
            const SizedBox(height: 10),
            _RecordOption(
              key: const Key('active-capture-source-device'),
              icon: FontAwesomeIcons.bluetooth,
              title: connectedDevice!.name,
              subtitle: context.l10n.connected,
              onTap: onPickDevice!,
            ),
          ],
        ],
      ),
    );
  }
}

class RecordOptionsSheet extends StatelessWidget {
  final VoidCallback onPickPhoneMic;
  final VoidCallback onPickPhoneCall;
  final String? connectedDeviceName;
  final VoidCallback? onPickConnectedDevice;
  final VoidCallback? onConnectDevice;
  final VoidCallback onImportAudio;

  const RecordOptionsSheet({
    super.key,
    required this.onPickPhoneMic,
    required this.onPickPhoneCall,
    this.connectedDeviceName,
    this.onPickConnectedDevice,
    this.onConnectDevice,
    required this.onImportAudio,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(16, 12, 16, MediaQuery.of(context).padding.bottom + 16),
      decoration: const BoxDecoration(
        color: Color(0xFF1F1F25),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 18),
          _RecordOption(
            key: const Key('record-source-phone-mic'),
            icon: FontAwesomeIcons.microphone,
            title: context.l10n.recordWithPhoneMic,
            subtitle: context.l10n.recordWithPhoneMicSubtitle,
            onTap: onPickPhoneMic,
          ),
          const SizedBox(height: 10),
          _RecordOption(
            key: const Key('record-source-phone-call'),
            icon: FontAwesomeIcons.phone,
            title: context.l10n.phoneCall,
            subtitle: context.l10n.phoneCallSubtitle,
            onTap: onPickPhoneCall,
          ),
          if (connectedDeviceName != null && onPickConnectedDevice != null) ...[
            const SizedBox(height: 10),
            _RecordOption(
              key: const Key('record-source-connected-device'),
              icon: FontAwesomeIcons.bluetooth,
              title: '${context.l10n.record}: $connectedDeviceName',
              subtitle: context.l10n.connected,
              onTap: onPickConnectedDevice!,
            ),
          ] else if (onConnectDevice != null) ...[
            const SizedBox(height: 10),
            _RecordOption(
              key: const Key('record-source-connect-device'),
              icon: FontAwesomeIcons.bluetooth,
              title: context.l10n.connectDevice,
              subtitle: context.l10n.connectDeviceMessage.replaceAll('\n', ' '),
              onTap: onConnectDevice!,
            ),
          ],
          const SizedBox(height: 10),
          _RecordOption(
            key: const Key('record-source-import-audio'),
            icon: FontAwesomeIcons.fileImport,
            title: '${context.l10n.importData}: ${context.l10n.recordings}',
            subtitle: 'MP3 · M4A · WAV · OGG · FLAC',
            onTap: onImportAudio,
          ),
        ],
      ),
    );
  }
}

class _RecordOption extends StatelessWidget {
  final FaIconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _RecordOption(
      {super.key, required this.icon, required this.title, required this.subtitle, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(color: const Color(0xFF2A2A33), borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              alignment: Alignment.center,
              decoration: const BoxDecoration(color: Color(0xFF35343B), shape: BoxShape.circle),
              child: FaIcon(icon, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text(subtitle, style: TextStyle(color: Colors.grey[400], fontSize: 12)),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: Colors.grey[500], size: 22),
          ],
        ),
      ),
    );
  }
}
