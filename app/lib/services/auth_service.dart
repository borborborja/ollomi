import 'dart:async';
import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';

class AuthService {
  static final instance = AuthService._();
  AuthService._() : _clientFactory = http.Client.new;
  AuthService.forTesting({required http.Client Function() clientFactory}) : _clientFactory = clientFactory;
  final http.Client Function() _clientFactory;
  static const _secure = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  final _changes = StreamController<AuthUserSnapshot?>.broadcast();
  final _expired = StreamController<AuthSessionExpiredEvent>.broadcast();
  AuthUserSnapshot? currentUser;
  Map<String, dynamic>? _session;
  Future<AuthTokenResult>? _refresh;
  int _generation = 0;
  Future<void> _storageQueue = Future.value();
  String serverUrl = '';
  String instanceId = '';
  String mcpUrl = '';
  Set<String> serverCapabilities = const {};
  bool get isAdmin => _session?['user']?['admin'] == true;
  bool supportsServerCapability(String capability) => serverCapabilities.contains(capability);
  Stream<AuthUserSnapshot?> get authStateChanges => _changes.stream;
  Stream<AuthSessionExpiredEvent> get sessionExpiredEvents => _expired.stream;
  bool isSignedIn() => currentUser != null;

  Future<void> initialize() async {
    final prefs = await SharedPreferences.getInstance();
    serverUrl = prefs.getString('ollomi.server') ?? '';
    instanceId = prefs.getString('ollomi.instance') ?? '';
    if (serverUrl.isNotEmpty) Env.overrideApiBaseUrl(serverUrl);
    final stored = await _secure.read(key: 'ollomi.session');
    if (stored != null) {
      final session = jsonDecode(stored) as Map<String, dynamic>;
      if (session['server'] == serverUrl && session['instance'] == instanceId) _apply(session);
    }
  }

  static String normalizeServer(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment) {
      throw const FormatException('Use an HTTP(S) URL without credentials.');
    }
    return '${uri.toString().replaceFirst(RegExp(r'/+$'), '')}/';
  }

  static String _serverForConnection(String value) {
    final server = normalizeServer(value);
    // A private LAN server may deliberately use HTTP, but a release APK must
    // never send a password to a public clear-text endpoint.
    Env.validateStartupRouting(
      productionFamily: true,
      configuredApiBaseUrl: server,
    );
    return server;
  }

  Future<Map<String, dynamic>> _request(
    String server,
    String path,
    Map<String, dynamic>? body,
  ) async {
    final client = _clientFactory();
    try {
      final request = http.Request(
        body == null ? 'GET' : 'POST',
        Uri.parse('$server$path'),
      )..followRedirects = false;
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);
      }
      final response = await http.Response.fromStream(
        await client.send(request).timeout(const Duration(seconds: 15)),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) throw LocalAuthError(response.statusCode);
      return jsonDecode(response.body) as Map<String, dynamic>;
    } finally {
      client.close();
    }
  }

  static void _validateServerInfo(Map<String, dynamic> info) {
    if (info['authentication'] != 'local' || info['protocol_version'] != 1 || info['instance_id'] is! String) {
      throw const FormatException('Incompatible Ollomi server.');
    }
  }

  Future<void> testServer(String address) async {
    final server = _serverForConnection(address);
    _validateServerInfo(await _request(server, 'v1/server-info', null));
  }

  Future<void> signIn(String address, String email, String password) async {
    final generation = ++_generation;
    final server = _serverForConnection(address);
    final info = await _request(server, 'v1/server-info', null);
    _validateServerInfo(info);
    final session = await _request(server, 'v1/auth/login', {
      'email': email.trim(),
      'password': password,
    });
    if (generation != _generation) throw const LocalAuthError(409);
    final prefs = await SharedPreferences.getInstance();
    final nextOwner = '$server|${info['instance_id']}|${session['user']['uid']}';
    final previousOwner = prefs.getString('ollomi.owner');
    if (previousOwner != nextOwner) {
      if (previousOwner != null) {
        final cached = {
          for (final key in prefs.getKeys())
            if (!key.startsWith('ollomi.') && !key.toLowerCase().contains('token')) key: prefs.get(key),
        };
        await prefs.setString(
          'ollomi.cache.$previousOwner',
          jsonEncode(cached),
        );
      }
      for (final key in prefs.getKeys().where((key) => !key.startsWith('ollomi.')).toList()) {
        await prefs.remove(key);
      }
      final cached = prefs.getString('ollomi.cache.$nextOwner');
      if (cached != null) {
        for (final entry in (jsonDecode(cached) as Map<String, dynamic>).entries) {
          final value = entry.value;
          if (value is String) await prefs.setString(entry.key, value);
          if (value is bool) await prefs.setBool(entry.key, value);
          if (value is int) await prefs.setInt(entry.key, value);
          if (value is double) await prefs.setDouble(entry.key, value);
          if (value is List) await prefs.setStringList(entry.key, value.cast<String>());
        }
      }
      await prefs.setString('ollomi.owner', nextOwner);
    }
    serverUrl = server;
    instanceId = info['instance_id'];
    await prefs.setString('ollomi.server', serverUrl);
    await prefs.setString('ollomi.instance', instanceId);
    Env.overrideApiBaseUrl(serverUrl);
    if (generation != _generation) return;
    await _save({
      ...session,
      'server': serverUrl,
      'instance': instanceId,
      'capabilities': info['capabilities'] is List ? info['capabilities'] : const <String>[],
      'mcp_url': info['mcp_url'] is String ? info['mcp_url'] : '',
    });
  }

  void _apply(Map<String, dynamic> session) {
    _session = session;
    final capabilities = session['capabilities'];
    serverCapabilities = capabilities is List ? capabilities.whereType<String>().toSet() : const {};
    mcpUrl = session['mcp_url'] is String ? session['mcp_url'] as String : '';
    final user = session['user'];
    currentUser = AuthUserSnapshot(
      uid: user['uid'],
      email: user['email'],
      displayName: user['display_name'],
    );
    final prefs = SharedPreferencesUtil();
    prefs.uid = currentUser!.uid;
    prefs.email = currentUser!.email ?? '';
    prefs.givenName = currentUser!.displayName ?? '';
    prefs.authToken = session['access_token'];
    prefs.tokenExpirationTime = DateTime.parse(
      session['expires_at'],
    ).millisecondsSinceEpoch;
    _changes.add(currentUser);
  }

  Future<void> _serialStorage(Future<void> Function() action) {
    final operation = _storageQueue.then((_) => action());
    _storageQueue = operation.catchError((Object _) {});
    return operation;
  }

  Future<void> _save(Map<String, dynamic> session) {
    final generation = _generation;
    return _serialStorage(() async {
      if (generation != _generation) return;
      await _secure.write(key: 'ollomi.session', value: jsonEncode(session));
      if (generation == _generation) _apply(session);
    });
  }

  Future<String?> getIdToken() async {
    if (_session == null) return null;
    if (DateTime.parse(
      _session!['expires_at'],
    ).isAfter(DateTime.now().add(const Duration(minutes: 1)))) {
      return _session!['access_token'];
    }
    return (await refreshIdToken()).tokenOrNull;
  }

  Future<AuthTokenResult> refreshIdToken() => _refresh ??= _rotate().whenComplete(() => _refresh = null);
  Future<AuthTokenResult> _rotate() async {
    if (_session == null) return const AuthTokenMissingUser();
    final generation = _generation;
    try {
      // The local refresh contract intentionally returns credentials and the
      // user only. Keep server-info metadata obtained at login so refreshing a
      // token cannot make optional features (notably MCP) disappear in-app.
      final previousSession = _session!;
      final result = await _request(serverUrl, 'v1/auth/refresh', {
        'refresh_token': previousSession['refresh_token'],
      });
      if (generation != _generation) return const AuthTokenMissingUser();
      await _save({
        ...result,
        'server': serverUrl,
        'instance': instanceId,
        'capabilities': previousSession['capabilities'] ?? const <String>[],
        'mcp_url': previousSession['mcp_url'] ?? '',
      });
      if (generation != _generation) return const AuthTokenMissingUser();
      return AuthTokenSuccess(
        token: result['access_token'],
        expirationTime: DateTime.parse(result['expires_at']),
      );
    } on LocalAuthError catch (error) {
      if (generation != _generation) return const AuthTokenMissingUser();
      if (error.status == 401) {
        await expireSession(
          const AuthSessionExpiredEvent(
            reason: AuthSessionExpirationReason.terminalTokenFailure,
          ),
        );
        return const AuthTokenTerminalFailure(code: 'session_expired');
      }
      return const AuthTokenTransientFailure(failureClass: 'server');
    } catch (_) {
      return const AuthTokenTransientFailure(failureClass: 'network');
    }
  }

  Future<void> signOut() async {
    final old = _session;
    _generation++;
    _session = null;
    currentUser = null;
    serverCapabilities = const {};
    mcpUrl = '';
    await _serialStorage(() => _secure.delete(key: 'ollomi.session'));
    SharedPreferencesUtil().clearUserDisplayCache();
    _changes.add(null);
    if (old != null) {
      try {
        await _request(old['server'], 'v1/auth/logout', {
          'refresh_token': old['refresh_token'],
        });
      } catch (_) {}
    }
  }

  Future<void> expireSession(AuthSessionExpiredEvent event) async {
    _expired.add(event);
    await signOut();
  }

  Future<void> updateGivenName(String name) async {
    final token = await getIdToken();
    final response = await http.patch(
      Uri.parse('${serverUrl}v1/users/me'),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'name': name}),
    );
    if (response.statusCode != 200) throw LocalAuthError(response.statusCode);
    if (_session != null) {
      await _save({
        ..._session!,
        'user': {..._session!['user'], 'display_name': name},
      });
    }
  }

  Future<void> restoreOnboardingState() async {
    SharedPreferencesUtil().onboardingCompleted = true;
  }

  void recordAuthenticatedRequest401({
    required bool recovered,
    required String outcome,
  }) {}
}

class LocalAuthError implements Exception {
  final int status;
  const LocalAuthError(this.status);
  @override
  String toString() => 'Server response: $status';
}
