import 'package:flutter/foundation.dart';

import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

enum SttResolvedPath {
  /// Ollomi's selected-server socket (`customSttConfig == null`).
  managed,

  /// Honor the user's persisted Custom STT config.
  honorCustom,

  /// Synthesized on-device config (`freemium:on-device`).
  onDevice,

  /// No transcription socket. Never a billed fallback.
  blocked,
}

class SttModeDecision {
  final SttResolvedPath path;
  final CustomSttConfig? customSttConfig;
  final String reason;
  final bool allowanceOnDevice;

  const SttModeDecision({
    required this.path,
    required this.reason,
    this.customSttConfig,
    this.allowanceOnDevice = false,
  });

  bool get opensManagedServerSocket => path == SttResolvedPath.managed;

  bool get blockSocket => path == SttResolvedPath.blocked;

  String get socketIdentity {
    if (blockSocket) return 'blocked';
    return customSttConfig?.sttConfigId ?? 'ollomi:server';
  }
}

/// Ollomi's STT policy is server-authoritative.
///
/// Historical Omi builds could send microphone audio directly to a provider
/// configured in phone storage, or fall back to a downloaded on-device model
/// when a cloud allowance changed. That would bypass the selected Ollomi
/// server, leak a provider key out of the server's `.env`, and make its model
/// fallback policy impossible to audit. The self-hosted fork always opens the
/// selected server's `/v4/listen` socket; that server owns provider selection,
/// retries and audio retention.
class SttModeResolver {
  static SttModeResolver instance = SttModeResolver();

  // Retain the legacy constructor parameters temporarily so old call sites and
  // tests can migrate without granting the client any STT routing authority.
  SttModeResolver({
    bool Function()? flagReader,
    Object? Function()? allowanceReader,
    Future<Object?> Function()? readinessReader,
    CustomSttConfig? Function()? onDeviceConfigBuilder,
  });

  @visibleForTesting
  static void debugResetInstance() {
    instance = SttModeResolver();
  }

  Future<SttModeDecision> decide({
    required CustomSttConfig persistedCustomStt,
    required BleAudioCodec codec,
  }) async =>
      const SttModeDecision(path: SttResolvedPath.managed, reason: 'selfhost_server');
}
