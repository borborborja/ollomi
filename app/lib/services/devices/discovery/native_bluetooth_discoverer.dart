import 'dart:async';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';
import 'device_discoverer.dart';

/// BLE discoverer backed by native platform APIs via Pigeon.
/// iOS: CoreBluetooth. Android: BluetoothLeScanner + CompanionDeviceManager.
class NativeBluetoothDiscoverer extends DeviceDiscoverer {
  final BleHostApi _hostApi = BleHostApi();

  @override
  String get name => 'NativeBluetooth';

  @override
  bool get isSupported => true;

  @override
  Future<DeviceDiscoveryResult> discover({int timeout = 5}) async {
    if (!await BluetoothReadiness.instance.ensureReady(BluetoothUse.discovery)) {
      return const DeviceDiscoveryResult(devices: [], isBlocked: true);
    }
    final List<BlePeripheral> results = [];
    final completer = Completer<void>();

    final previousCallback = BleBridge.instance.peripheralDiscoveredCallback;

    BleBridge.instance.peripheralDiscoveredCallback = (BlePeripheral peripheral) {
      // Some devices advertise only their service UUID; keep them until
      // classification so they are not discarded before a scan-response name.
      final previousIndex = results.indexWhere((p) => p.uuid == peripheral.uuid);
      if (previousIndex < 0) {
        results.add(peripheral);
      } else {
        final previous = results.removeAt(previousIndex);
        results.add(BlePeripheral(
          uuid: peripheral.uuid,
          name: peripheral.name.isNotEmpty ? peripheral.name : previous.name,
          rssi: peripheral.rssi,
          serviceUuids: {...previous.serviceUuids, ...peripheral.serviceUuids}.toList(),
        ));
      }
    };

    try {
      await _hostApi.startScan(timeout, []);

      // Wait for scan to complete
      Timer(Duration(seconds: timeout), () {
        if (!completer.isCompleted) completer.complete();
      });
      await completer.future;

      await _hostApi.stopScan();

      final devices = results.map(deviceForPeripheral).whereType<BtDevice>().toList()
        ..sort((a, b) => b.rssi.compareTo(a.rssi));

      return DeviceDiscoveryResult(devices: devices);
    } finally {
      BleBridge.instance.peripheralDiscoveredCallback = previousCallback;
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _hostApi.stopScan();
    } catch (e) {
      Logger.debug('NativeBluetoothDiscoverer: stop scan error: $e');
    }
  }

  // MARK: - Device type detection (mirrors BtDevice.isSupportedDevice without ScanResult)

  static bool _isBee(BlePeripheral p) {
    return p.name.toLowerCase().contains('bee');
  }

  static bool _isPlaud(BlePeripheral p) {
    return p.name.toUpperCase().startsWith('PLAUD');
  }

  static bool _isFieldy(BlePeripheral p) {
    final name = p.name.toLowerCase();
    return name == 'compass' || name == 'fieldy' || _hasService(p, fieldyServiceUuid);
  }

  static bool _isFriendPendant(BlePeripheral p) {
    return p.name.toLowerCase().startsWith('friend_') || _hasService(p, friendPendantServiceUuid);
  }

  static bool _isLimitless(BlePeripheral p) {
    final name = p.name.toLowerCase();
    return name.contains('limitless') || name.contains('pendant') || _hasService(p, limitlessServiceUuid);
  }

  static bool _isOmi(BlePeripheral p) {
    final name = p.name.trim().toLowerCase();
    // CV1 and the original Friend devkit can advertise a name without the
    // custom service UUID in the Android scan record.
    return _hasService(p, omiServiceUuid) ||
        name == 'omi' ||
        name.startsWith('omi ') ||
        name.startsWith('omi_') ||
        name.startsWith('omi-') ||
        name.startsWith('omiglass') ||
        name == 'friend';
  }

  static bool _hasService(BlePeripheral p, String serviceUuid) {
    final target = serviceUuid.toLowerCase();
    return p.serviceUuids.any((uuid) => uuid.toLowerCase() == target);
  }

  static BtDevice? deviceForPeripheral(BlePeripheral p) {
    if (!(_isBee(p) || _isPlaud(p) || _isFieldy(p) || _isFriendPendant(p) || _isLimitless(p) || _isOmi(p))) {
      return null;
    }
    DeviceType type;
    if (_isBee(p)) {
      type = DeviceType.bee;
    } else if (_isPlaud(p)) {
      type = DeviceType.plaud;
    } else if (_isFieldy(p)) {
      type = DeviceType.fieldy;
    } else if (_isFriendPendant(p)) {
      type = DeviceType.friendPendant;
    } else if (_isLimitless(p)) {
      type = DeviceType.limitless;
    } else if (_isOmi(p)) {
      type = DeviceType.omi;
    } else {
      type = DeviceType.omi;
    }

    return BtDevice(
      name: p.name.isNotEmpty ? p.name : (type == DeviceType.friendPendant ? 'Friend Pendant' : 'Omi'),
      id: p.uuid,
      type: type,
      rssi: p.rssi,
      locator: DeviceLocator.bluetooth(deviceId: p.uuid),
    );
  }
}
