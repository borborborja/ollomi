import 'package:omi/env/env.dart';

// Public sharing is optional and must never default to an upstream Omi host.
// If a deployment deliberately exposes compatible public-share routes, it may
// override the selected Ollomi server at build time.
//
// Override with `--dart-define=OLLOMI_SHARE_BASE_URL=https://share.example.com`.

/// Public-share origins are always normalized without a trailing slash.
/// Keep this independent from the API client base, whose slash is intentional.
const defaultShareBaseUrl = 'http://127.0.0.1:8080';

const _shareBaseFromDefine = String.fromEnvironment('OLLOMI_SHARE_BASE_URL');

final _hostOk = RegExp(r'^[A-Za-z0-9.-]+$');

/// Return the configured share origin (no trailing slash).
///
/// [raw] is for tests; production callers omit it so the dart-define / default apply.
String shareBaseUrl([String? raw]) {
  var value = (raw ?? _shareBaseFromDefine).trim();
  if (value.isEmpty) {
    value = Env.apiBaseUrl;
  }
  if (!value.contains('://')) {
    value = 'https://$value';
  }
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.scheme != 'http' && uri.scheme != 'https') ||
      !_hostOk.hasMatch(uri.host)) {
    return shareBaseUrl('');
  }
  final origin = uri.hasPort ? '${uri.scheme}://${uri.host}:${uri.port}' : '${uri.scheme}://${uri.host}';
  final path = uri.path.replaceFirst(RegExp(r'/+$'), '');
  if (path.isEmpty || path == '/') {
    return origin;
  }
  return '$origin$path';
}

/// Join [shareBaseUrl] with a path (leading slash optional).
String buildShareUrl(String path, {String? raw}) {
  final normalized = path.startsWith('/') ? path : '/$path';
  return '${shareBaseUrl(raw)}$normalized';
}

String conversationShareUrl(String conversationId, {String? raw}) =>
    buildShareUrl('/conversations/$conversationId', raw: raw);

String appShareUrl(String appId, {String? raw}) => buildShareUrl('/apps/$appId', raw: raw);

String recapShareUrl(String summaryId, {String? raw}) => buildShareUrl('/recaps/$summaryId', raw: raw);
