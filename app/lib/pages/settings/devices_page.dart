import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/models/device_connect_policy.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/omi_confirm_dialog.dart';

/// Known devices, in connection-priority order.
///
/// The first entry with auto-connect enabled that is actually advertising is
/// the device the app connects to. A manual tap replaces the active device;
/// while a one-off recording is in progress the user confirms first.
class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key});

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  late List<BtDevice> _devices;

  @override
  void initState() {
    super.initState();
    _devices = SharedPreferencesUtil().btDevices;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final provider = context.read<DeviceProvider>();
      provider.clearAutoConnectSuppression();
      provider.refreshKnownDeviceAvailability();
    });
  }

  void _reload() {
    setState(() => _devices = SharedPreferencesUtil().btDevices);
  }

  Future<void> _reorder(int oldIndex, int newIndex) async {
    setState(() {
      if (newIndex > oldIndex) newIndex -= 1;
      final moved = _devices.removeAt(oldIndex);
      _devices.insert(newIndex, moved);
    });
    await SharedPreferencesUtil().reorderKnownDevices(_devices.map((device) => device.id).toList());
  }

  String _recordPolicyLabel(BuildContext context, DeviceRecordingOnConnect policy) {
    return switch (policy) {
      DeviceRecordingOnConnect.none => context.l10n.recordingOnConnectNone,
      DeviceRecordingOnConnect.continuous => context.l10n.continuousRecording,
      DeviceRecordingOnConnect.oneOff => context.l10n.recordingOnConnectOneOff,
    };
  }

  Future<void> _connect(DeviceProvider provider, BtDevice device) async {
    if (provider.connectedDevice?.id == device.id || provider.pairedDevice?.id == device.id) return;
    final capture = context.read<CaptureProvider>();
    final oneOffActive = capture.isCaptureActive && !capture.continuousCaptureEnabled;
    if (oneOffActive) {
      final confirmed = await OmiConfirmDialog.show(
        context,
        title: context.l10n.activeCaptureButtonSwitchSource,
        message: context.l10n.switchAndRestart,
        confirmLabel: context.l10n.switchAndRestart,
        confirmColor: const Color(0xFFFE5D50),
      );
      if (confirmed != true || !mounted) return;
    }
    await provider.connectToKnownDevice(device, confirmedStop: oneOffActive);
  }

  Future<void> _forget(DeviceProvider provider, BtDevice device) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.forgetDevice,
      message: context.l10n.forgetDeviceConfirm,
      confirmLabel: context.l10n.forgetDevice,
      confirmColor: const Color(0xFFFE5D50),
    );
    if (confirmed != true || !mounted) return;
    if (provider.connectedDevice?.id == device.id) {
      provider.suppressAutoConnect();
      await ServiceManager.instance().device.forgetDevice(device.id);
      try {
        BleHostApi().unmanageDevice(device.id);
      } catch (_) {}
      provider.setIsConnected(false);
      await provider.setConnectedDevice(null);
    }
    await SharedPreferencesUtil().forgetKnownDevice(device.id);
    if (mounted) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<DeviceProvider, CaptureProvider>(
      builder: (context, provider, capture, child) {
        final preferences = SharedPreferencesUtil();
        final masterEnabled = preferences.autoConnectEnabled;

        return Scaffold(
          backgroundColor: const Color(0xFF0D0D0D),
          appBar: AppBar(
            backgroundColor: const Color(0xFF0D0D0D),
            elevation: 0,
            title: Text(
              context.l10n.devices,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
            ),
            actions: [
              IconButton(
                key: const Key('devices_refresh_availability'),
                tooltip: context.l10n.refresh,
                icon: const Icon(Icons.refresh, color: Colors.white),
                onPressed: () => provider.refreshKnownDeviceAvailability(),
              ),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            children: [
              _buildMasterSwitch(preferences, masterEnabled),
              const SizedBox(height: 12),
              if (!preferences.backgroundModeEnabled) ...[
                _buildBackgroundModeWarning(context),
                const SizedBox(height: 12),
              ],
              if (_devices.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 48),
                  child: Center(
                    child: Text(
                      context.l10n.connectDevice,
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
                    ),
                  ),
                )
              else ...[
                Padding(
                  padding: const EdgeInsets.only(left: 4, bottom: 8),
                  child: Text(
                    context.l10n.priorityOrderHint,
                    style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13),
                  ),
                ),
                ReorderableListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  buildDefaultDragHandles: false,
                  itemCount: _devices.length,
                  onReorder: _reorder,
                  itemBuilder: (context, index) {
                    final device = _devices[index];
                    return _buildDeviceCard(context, provider, capture, device, index);
                  },
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildMasterSwitch(SharedPreferencesUtil preferences, bool enabled) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
      child: SwitchListTile(
        key: const Key('auto_connect_master_switch'),
        value: enabled,
        activeThumbColor: Colors.white,
        activeTrackColor: const Color(0xFFFE5D50),
        title: Text(context.l10n.autoConnect, style: const TextStyle(color: Colors.white, fontSize: 16)),
        contentPadding: EdgeInsets.zero,
        onChanged: (value) {
          preferences.autoConnectEnabled = value;
          if (mounted) setState(() {});
        },
      ),
    );
  }

  Widget _buildBackgroundModeWarning(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFB800).withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFFFB800).withValues(alpha: 0.25)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const FaIcon(FontAwesomeIcons.circleExclamation, color: Color(0xFFFFB800), size: 15),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              context.l10n.backgroundModeRequired,
              style: const TextStyle(color: Color(0xFFFFB800), fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDeviceCard(
    BuildContext context,
    DeviceProvider provider,
    CaptureProvider capture,
    BtDevice device,
    int index,
  ) {
    final preferences = SharedPreferencesUtil();
    final isActive = provider.connectedDevice?.id == device.id || provider.pairedDevice?.id == device.id;
    final available = provider.isDeviceAvailable(device.id);
    final statusLabel = isActive
        ? context.l10n.connected
        : available
            ? context.l10n.available
            : context.l10n.offline;
    final statusColor = isActive
        ? const Color(0xFF4CAF50)
        : available
            ? const Color(0xFF8E8E93)
            : const Color(0xFFB3261E);

    return Container(
      key: ValueKey('known-device-${device.id}'),
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(6, 6, 12, 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: isActive ? const Color(0xFF4CAF50).withValues(alpha: 0.4) : const Color(0xFF2A2A2E)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              ReorderableDragStartListener(
                index: index,
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 6, vertical: 8),
                  child: Icon(Icons.drag_indicator, color: Color(0xFF8E8E93), size: 20),
                ),
              ),
              SizedBox(
                width: 22,
                height: 22,
                child: Image.asset(DeviceUtils.getDeviceImageFromBtDevice(device), fit: BoxFit.contain),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      DeviceUtils.displayName(device, fallback: device.id),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      statusLabel,
                      style: TextStyle(color: statusColor, fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
              if (isActive)
                IconButton(
                  key: const Key('known_device_settings'),
                  tooltip: context.l10n.deviceSettings,
                  icon: const Icon(Icons.settings, color: Color(0xFF8E8E93), size: 20),
                  onPressed: () => Navigator.of(
                    context,
                  ).push(MaterialPageRoute(builder: (_) => const DeviceSettings())),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              const SizedBox(width: 34),
              Expanded(
                child: Row(
                  children: [
                    Text(
                      context.l10n.autoConnect,
                      style: TextStyle(color: preferences.autoConnectEnabled ? Colors.white : const Color(0xFF636366),
                          fontSize: 13),
                    ),
                    Switch(
                      key: Key('device_auto_connect_${device.id}'),
                      value: preferences.deviceAutoConnectFor(device.id),
                      activeThumbColor: Colors.white,
                      activeTrackColor: const Color(0xFFFE5D50),
                      onChanged: preferences.autoConnectEnabled
                          ? (value) async {
                              await preferences.setDeviceAutoConnectFor(device.id, value);
                              if (mounted) setState(() {});
                            }
                          : null,
                    ),
                  ],
                ),
              ),
              PopupMenuButton<DeviceRecordingOnConnect>(
                key: Key('device_recording_policy_${device.id}'),
                tooltip: context.l10n.recordingOnConnect,
                color: const Color(0xFF2A2A2E),
                initialValue: preferences.deviceRecordingOnConnectFor(device.id),
                onSelected: (value) async {
                  await preferences.setDeviceRecordingOnConnectFor(device.id, value);
                  if (mounted) setState(() {});
                },
                itemBuilder: (context) => [
                  for (final policy in DeviceRecordingOnConnect.values)
                    PopupMenuItem(
                      value: policy,
                      child: Text(_recordPolicyLabel(context, policy), style: const TextStyle(color: Colors.white)),
                    ),
                ],
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2A2A2E),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    _recordPolicyLabel(context, preferences.deviceRecordingOnConnectFor(device.id)),
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                key: Key('device_connect_${device.id}'),
                onTap: isActive ? null : () => _connect(provider, device),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: isActive ? const Color(0xFF2A2A2E) : const Color(0xFFFE5D50),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    isActive ? context.l10n.connected : context.l10n.connectNow,
                    style: TextStyle(color: isActive ? const Color(0xFF8E8E93) : Colors.black, fontSize: 12),
                  ),
                ),
              ),
              IconButton(
                key: Key('device_forget_${device.id}'),
                tooltip: context.l10n.forgetDevice,
                icon: const Icon(Icons.delete_outline, color: Colors.redAccent, size: 20),
                onPressed: () => _forget(provider, device),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
