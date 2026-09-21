import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';

void main() {
  group('Ollomi server-authoritative STT routing', () {
    test('ignores a persisted direct-provider key and routes through Ollomi', () async {
      const legacyDirectProvider = CustomSttConfig(
        provider: SttProvider.deepgramLive,
        apiKey: 'must-not-leave-the-phone',
        url: 'wss://api.deepgram.com/v1/listen',
      );

      final decision = await SttModeResolver().decide(
        persistedCustomStt: legacyDirectProvider,
        codec: BleAudioCodec.opus,
      );

      expect(decision.path, SttResolvedPath.managed);
      expect(decision.customSttConfig, isNull);
      expect(decision.reason, 'selfhost_server');
      expect(decision.socketIdentity, 'ollomi:server');
      expect(decision.opensManagedServerSocket, isTrue);
    });

    test('uses the same server route for every legacy codec and model mode', () async {
      const legacyOnDeviceModel = CustomSttConfig(
        provider: SttProvider.onDeviceWhisper,
        url: '/local/model.bin',
      );

      final decision = await SttModeResolver().decide(
        persistedCustomStt: legacyOnDeviceModel,
        codec: BleAudioCodec.aac,
      );

      expect(decision.path, SttResolvedPath.managed);
      expect(decision.customSttConfig, isNull);
      expect(decision.blockSocket, isFalse);
    });
  });
}
