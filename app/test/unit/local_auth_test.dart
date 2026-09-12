import 'dart:async';
import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/auth/auth_token_result.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('com.omi/native'), (_) async => null);
    await SharedPreferencesUtil.init();
  });
  Map<String, dynamic> session(String token) => {
        'access_token': token,
        'refresh_token': 'refresh-$token',
        'expires_at': DateTime.now().add(const Duration(hours: 1)).toIso8601String(),
        'user': {'uid': 'owner-1', 'email': 'owner@local', 'display_name': 'Owner', 'admin': true},
      };
  test('normalizes server paths and rejects credentials and ambiguous URLs', () {
    expect(AuthService.normalizeServer(' http://192.168.1.2:8080/root/// '), 'http://192.168.1.2:8080/root/');
    for (final value in ['file:///tmp/a', 'example.com', 'https://u:p@example.com', 'https://example.com?token=x']) {
      expect(() => AuthService.normalizeServer(value), throwsFormatException);
    }
  });
  test('local login persists the selected instance and logout erases the session', () async {
    final calls = <http.Request>[];
    final service = AuthService.forTesting(
        clientFactory: () => MockClient((request) async {
              calls.add(request);
              if (request.url.path == '/v1/server-info') {
                return http.Response(
                    jsonEncode({'authentication': 'local', 'protocol_version': 1, 'instance_id': 'server-a'}), 200);
              }
              if (request.url.path == '/v1/auth/login') return http.Response(jsonEncode(session('first')), 200);
              return http.Response('{}', 200);
            }));
    await service.signIn('http://192.168.1.2:8080', 'owner@local', 'password');
    expect(await service.getIdToken(), 'first');
    expect(service.instanceId, 'server-a');
    expect(service.isAdmin, isTrue);
    expect(calls.every((request) => request.followRedirects == false), isTrue);
    await service.signOut();
    expect(service.currentUser, isNull);
    expect(await const FlutterSecureStorage().read(key: 'ollomi.session'), isNull);
  });
  test('an old refresh rejection cannot log out a newly selected account', () async {
    final refresh = Completer<http.Response>();
    final service = AuthService.forTesting(
        clientFactory: () => MockClient((request) async {
              if (request.url.path == '/v1/server-info') {
                return http.Response(
                    jsonEncode({'authentication': 'local', 'protocol_version': 1, 'instance_id': request.url.host}),
                    200);
              }
              if (request.url.path == '/v1/auth/login') {
                return http.Response(jsonEncode(session(request.url.host)), 200);
              }
              if (request.url.path == '/v1/auth/refresh') return refresh.future;
              return http.Response('{}', 200);
            }));
    await service.signIn('http://first.local', 'owner@local', 'password');
    final pending = service.refreshIdToken();
    await service.signIn('http://second.local', 'owner@local', 'password');
    refresh.complete(http.Response('{}', 401));
    expect(await pending, isA<AuthTokenMissingUser>());
    expect(await service.getIdToken(), 'second.local');
    await service.signOut();
  });
  test('a pending login cannot restore a session after logout', () async {
    final login = Completer<http.Response>();
    final entered = Completer<void>();
    final service = AuthService.forTesting(
        clientFactory: () => MockClient((request) async {
              if (request.url.path == '/v1/server-info') {
                return http.Response(
                    jsonEncode({'authentication': 'local', 'protocol_version': 1, 'instance_id': 'a'}), 200);
              }
              entered.complete();
              return login.future;
            }));
    final pending = service.signIn('http://first.local', 'owner@local', 'password');
    final assertion = expectLater(pending, throwsA(isA<LocalAuthError>()));
    await entered.future;
    await service.signOut();
    login.complete(http.Response(jsonEncode(session('old')), 200));
    await assertion;
    expect(service.currentUser, isNull);
  });
}
