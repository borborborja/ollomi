import 'package:flutter/foundation.dart';

import 'package:omi/flavors.dart';

import 'environment_profile.dart';

abstract class Env {
  static const productionApiBaseUrl = 'http://127.0.0.1:8080/';
  static const _apiBaseUrlFromDefine = String.fromEnvironment('OLLOMI_API_BASE_URL');
  static EnvFields _instance = LocalEnvFields();
  static String? _apiBaseUrlOverride;
  static bool isTestFlight = false;

  static AppEnvironmentProfile get profile =>
      AppEnvironmentProfile.forFlavor(productionFlavor: F.env == Environment.prod);

  static void init(EnvFields instance) {
    _instance = instance;
  }

  static void overrideApiBaseUrl(String url) {
    _apiBaseUrlOverride = url;
  }

  static void clearApiBaseUrlOverrideForTesting() {
    _apiBaseUrlOverride = null;
  }

  static String? get posthogApiKey => _instance.posthogApiKey;

  static String? get apiBaseUrl {
    if (_apiBaseUrlOverride != null) return _apiBaseUrlOverride;
    if (_apiBaseUrlFromDefine.isNotEmpty) return _apiBaseUrlFromDefine;
    return _instance.apiBaseUrl ?? productionApiBaseUrl;
  }

  static String get authCallbackScheme => profile.authCallbackScheme;

  static String get authRedirectUri => '$authCallbackScheme://auth/callback';

  /// Local identity and product requests always use the same selected backend.
  static String get authApiBaseUrl => authApiBaseUrlForProfile(profile, servingApiBaseUrl: apiBaseUrl);

  static String authApiBaseUrlForProfile(AppEnvironmentProfile configuredProfile, {String? servingApiBaseUrl}) {
    return servingApiBaseUrl ?? productionApiBaseUrl;
  }

  /// An Ollomi APK is deliberately not pinned to an upstream cloud authority.
  /// It accepts a valid HTTP(S) address until the setup wizard persists the
  /// selected server; deployments should normally use HTTPS.
  static void validateStartupRouting({
    required bool productionFamily,
    String? configuredApiBaseUrl,
    AppEnvironmentProfile? configuredProfile,
    bool releaseBuild = kReleaseMode,
  }) {
    final effectiveProfile = configuredProfile ?? (productionFamily ? AppEnvironmentProfile.production : profile);
    final normalized = (configuredApiBaseUrl ?? apiBaseUrl ?? '').trim().replaceFirst(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(normalized);
    if (uri == null || uri.host.isEmpty || (uri.scheme != 'http' && uri.scheme != 'https')) {
      throw StateError('Profile ${effectiveProfile.name} requires a valid HTTP(S) API endpoint.');
    }
    if (releaseBuild && productionFamily && uri.scheme != 'https' && !_isLocalDevelopmentApi(normalized)) {
      throw StateError('A release build requires HTTPS unless the Ollomi server is on a private network.');
    }
  }

  static void requireProductionRouting() => validateStartupRouting(productionFamily: true);

  static bool _isLocalDevelopmentApi(String base) {
    final uri = Uri.tryParse(base);
    if (uri == null || uri.host.isEmpty || (uri.scheme != 'http' && uri.scheme != 'https')) {
      return false;
    }
    final host = uri.host.toLowerCase();
    if (host == 'localhost' || host == 'host.docker.internal' || host == '::1') {
      return true;
    }
    // RFC 4193 unique-local IPv6. Public IPv6 endpoints still require HTTPS;
    // a ULA can legitimately be a LAN-only Ollomi server, just like RFC 1918
    // IPv4. Uri has already validated the host before this check.
    if (host.contains(':')) {
      final firstHextet = int.tryParse(host.split(':').first, radix: 16);
      return firstHextet != null && (firstHextet & 0xfe00) == 0xfc00;
    }
    final octets = host.split('.').map(int.tryParse).toList();
    if (octets.length != 4 || octets.any((octet) => octet == null || octet < 0 || octet > 255)) {
      return false;
    }
    final first = octets[0]!;
    final second = octets[1]!;
    return first == 10 ||
        (first == 172 && second >= 16 && second <= 31) ||
        (first == 192 && second == 168) ||
        // 100.64.0.0/10 — RFC 6598 shared address space, the range Tailscale
        // assigns. Included because a physical device has no other route to a
        // developer's local harness: the harness binds loopback only by design,
        // so the device cannot use 127.x, and a plain LAN address does not reach
        // it either. Bounded to the real /10 — 100.63.x and 100.128.x are public.
        (first == 100 && second >= 64 && second <= 127) ||
        (first == 127);
  }

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;
}

abstract class EnvFields {
  String? get posthogApiKey;

  String? get apiBaseUrl;

  String? get intercomAppId;

  String? get intercomIOSApiKey;

  String? get intercomAndroidApiKey;

  // Compatibility fields for retained Flutter test fixtures. They are not
  // consumed by Ollomi authentication or startup.
  String? get googleClientId;

  String? get googleClientSecret;

  bool? get useWebAuth;

  bool? get useAuthCustomToken;
}

class LocalEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => null;
  @override
  String? get posthogApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}
