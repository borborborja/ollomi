import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/widgets/widget_bridge.dart';
import 'package:omi/services/widgets/widget_state.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.ollomi.widgets');
  final calls = <MethodCall>[];

  setUp(() {
    calls.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      if (call.method == 'consumePendingAction') return 'start_continuous';
      return true;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
  });

  test('pushState sends the encoded state', () async {
    final bridge = WidgetBridge();

    await bridge.pushState(const OllomiWidgetState(recording: true, source: 'Omi'));

    expect(calls.single.method, 'updateState');
    expect(calls.single.arguments['state'], contains('"recording":true'));
  });

  test('consumePendingAction returns the native action and clears to null', () async {
    final bridge = WidgetBridge();

    expect(await bridge.consumePendingAction(), 'start_continuous');
  });

  test('a missing channel does not throw', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
    final bridge = WidgetBridge();

    await bridge.pushState(const OllomiWidgetState());
    expect(await bridge.consumePendingAction(), isNull);
  });

  test('onWidgetAction reaches the registered handler', () async {
    final bridge = WidgetBridge();
    String? received;
    bridge.setActionHandler((action) => received = action);

    await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.handlePlatformMessage(
      'com.ollomi.widgets',
      const StandardMethodCodec().encodeMethodCall(const MethodCall('onWidgetAction', 'stop')),
      (_) {},
    );
    await Future<void>.delayed(Duration.zero);

    expect(received, 'stop');
  });
}
