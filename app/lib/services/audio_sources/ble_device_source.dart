import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/audio_sources/audio_source.dart';

/// Audio source for Omi/OpenGlass BLE devices.
///
/// BLE devices prepend a 3-byte firmware header to each audio packet:
///   [packet_id_low, packet_id_high, packet_index]
///
/// Opus frames can span several notifications at small MTUs. The next frame's
/// index-zero packet confirms that the preceding frame is complete.
class BleDeviceSource implements AudioSource {
  static const int headerSize = 3;
  static const int maxOpusFrameBytes = 1275;
  List<int>? _pending;
  FrameSyncKey? _pendingKey;
  int? _lastPacketId;
  int? _lastFragmentIndex;

  @override
  final BleAudioCodec codec;

  @override
  final String deviceId;

  @override
  final String deviceModel;

  BleDeviceSource({
    required this.codec,
    required this.deviceId,
    required this.deviceModel,
  });

  @override
  List<WalFrame> processBytes(List<int> rawBytes) {
    if (rawBytes.length <= headerSize) return [];
    if (!codec.isOpusSupported()) {
      return [WalFrame(payload: rawBytes.sublist(headerSize), syncKey: FrameSyncKey.fromBleHeader(rawBytes))];
    }
    final packetId = rawBytes[0] | (rawBytes[1] << 8);
    final fragmentIndex = rawBytes[2];
    final continuous = _lastPacketId != null && packetId == ((_lastPacketId! + 1) & 0xffff);
    if (fragmentIndex == 0) {
      final completed = continuous && _pending != null && _pendingKey != null
          ? [WalFrame(payload: _pending!, syncKey: _pendingKey!)]
          : <WalFrame>[];
      _pending = rawBytes.sublist(headerSize);
      _pendingKey = FrameSyncKey.fromBleHeader(rawBytes);
      _lastPacketId = packetId;
      _lastFragmentIndex = 0;
      return completed;
    }
    if (!continuous || _pending == null || fragmentIndex != _lastFragmentIndex! + 1 ||
        _pending!.length + rawBytes.length - headerSize > maxOpusFrameBytes) {
      _reset();
      return [];
    }
    _pending!.addAll(rawBytes.sublist(headerSize));
    _lastPacketId = packetId;
    _lastFragmentIndex = fragmentIndex;
    return [];
  }

  @override
  List<int> getSocketPayload(List<int> rawBytes) {
    return rawBytes.length > headerSize ? rawBytes.sublist(headerSize) : const [];
  }

  @override
  List<WalFrame> flush() {
    // Without the following index-zero packet, a final fragment may be missing.
    _reset();
    return [];
  }

  void _reset() {
    _pending = null;
    _pendingKey = null;
    _lastPacketId = null;
    _lastFragmentIndex = null;
  }
}
