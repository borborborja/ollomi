import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';

class _FakeWal implements IWalService {
  bool started = false;

  @override
  void start() => started = true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  test('starting app services makes Bluetooth discovery ready', () async {
    final device = DeviceService();
    final wal = _FakeWal();
    final manager = ServiceManager.forTesting(device: device, wal: wal);

    expect(device.status, DeviceServiceStatus.init);
    await manager.start();
    expect(device.status, DeviceServiceStatus.ready);
    expect(wal.started, isTrue);
  });
}
