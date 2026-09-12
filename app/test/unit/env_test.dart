import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';

void main() {
  tearDown(Env.clearApiBaseUrlOverrideForTesting);
  test('an unconfigured installation only addresses localhost', () {
    Env.clearApiBaseUrlOverrideForTesting();
    expect(Env.apiBaseUrl, 'http://127.0.0.1:8080/');
  });
  test('authentication follows the selected backend for every flavor', () {
    for (final profile in AppEnvironmentProfile.values) {
      expect(Env.authApiBaseUrlForProfile(profile, servingApiBaseUrl: 'https://private.example/root/'),
          'https://private.example/root/');
    }
    Env.overrideApiBaseUrl('http://192.168.1.4:8080/');
    expect(Env.apiBaseUrl, 'http://192.168.1.4:8080/');
    expect(Env.authApiBaseUrl, Env.apiBaseUrl);
  });
  test('startup restores local authentication before application services', () {
    final source = File('lib/main.dart').readAsStringSync();
    expect(source, contains('AuthService.instance.initialize()'));
    expect(source.indexOf('AuthService.instance.initialize()'), lessThan(source.indexOf('ServiceManager.init()')));
    expect(source, isNot(contains('Firebase.initializeApp')));
  });
}
