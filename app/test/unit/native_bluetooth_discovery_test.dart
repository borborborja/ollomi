import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/discovery/native_bluetooth_discoverer.dart';
import 'package:omi/services/devices/models.dart';

BlePeripheral peripheral(String name, {List<String> services = const []}) => BlePeripheral(
      uuid: 'AA:BB:CC:DD:EE:FF',
      name: name,
      rssi: -50,
      serviceUuids: services,
    );

void main() {
  test('discovers Omi CV1 by name when its service is absent from the scan record', () {
    final device = NativeBluetoothDiscoverer.deviceForPeripheral(peripheral('Omi'));
    expect(device?.type, DeviceType.omi);
    expect(device?.name, 'Omi');
  });

  test('discovers original Friend devkit separately from LC3 Friend Pendant', () {
    expect(NativeBluetoothDiscoverer.deviceForPeripheral(peripheral('Friend'))?.type, DeviceType.omi);
    expect(NativeBluetoothDiscoverer.deviceForPeripheral(peripheral('Friend_123'))?.type, DeviceType.friendPendant);
  });

  test('discovers unnamed Omi by service and rejects unrelated peripherals', () {
    final omi = NativeBluetoothDiscoverer.deviceForPeripheral(peripheral('', services: [omiServiceUuid]));
    expect(omi?.type, DeviceType.omi);
    expect(omi?.name, 'Omi');
    expect(NativeBluetoothDiscoverer.deviceForPeripheral(peripheral('Headphones')), isNull);
  });
}
