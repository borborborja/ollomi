import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';

void main() {
  tearDown(Env.clearApiBaseUrlOverrideForTesting);
  test('an unconfigured installation only addresses localhost', () {
    Env.clearApiBaseUrlOverrideForTesting();
    expect(Env.apiBaseUrl, 'http://127.0.0.1:8080/');
    for (final profile in AppEnvironmentProfile.values) {
      expect(Uri.parse(profile.defaultApiBaseUrl).host, '127.0.0.1');
    }
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
  test('a release APK permits HTTP only for a private Ollomi server', () {
    expect(
      () => Env.validateStartupRouting(
        productionFamily: true,
        configuredApiBaseUrl: 'http://ollomi.example.test/',
        releaseBuild: true,
      ),
      throwsStateError,
    );
    expect(
      () => Env.validateStartupRouting(
        productionFamily: true,
        configuredApiBaseUrl: 'http://192.168.1.20:8080/',
        releaseBuild: true,
      ),
      returnsNormally,
    );
    expect(
      () => Env.validateStartupRouting(
        productionFamily: true,
        configuredApiBaseUrl: 'http://[fd42:1234::20]:8080/',
        releaseBuild: true,
      ),
      returnsNormally,
    );
    expect(
      () => Env.validateStartupRouting(
        productionFamily: true,
        configuredApiBaseUrl: 'https://ollomi.example.test/',
        releaseBuild: true,
      ),
      returnsNormally,
    );
  });
  test('startup restores local authentication before application services', () {
    final source = File('lib/main.dart').readAsStringSync();
    expect(source, contains('AuthService.instance.initialize()'));
    expect(source.indexOf('AuthService.instance.initialize()'), lessThan(source.indexOf('ServiceManager.init()')));
    expect(source, isNot(contains('Firebase.initializeApp')));
  });
}
