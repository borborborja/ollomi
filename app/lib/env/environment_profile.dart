/// Runtime routing profiles for the self-hosted Ollomi app.
///
/// The chosen Ollomi server is persisted after the setup wizard; these values
/// are only safe fallbacks before the first sign-in. They deliberately contain
/// neither cloud identity nor upstream Omi endpoints.
enum AppEnvironmentProfile {
  localDev(
    name: 'local_dev',
    defaultApiBaseUrl: 'http://127.0.0.1:8080/',
    authCallbackScheme: 'ollomi-dev',
  ),
  production(
    name: 'production',
    defaultApiBaseUrl: 'http://127.0.0.1:8080/',
    authCallbackScheme: 'ollomi',
  );

  const AppEnvironmentProfile({
    required this.name,
    required this.defaultApiBaseUrl,
    required this.authCallbackScheme,
  });

  final String name;
  final String defaultApiBaseUrl;
  final String authCallbackScheme;

  static AppEnvironmentProfile forFlavor({required bool productionFlavor}) {
    const requested = String.fromEnvironment('OLLOMI_APP_PROFILE');
    if (requested.isEmpty) {
      return productionFlavor ? AppEnvironmentProfile.production : AppEnvironmentProfile.localDev;
    }

    return AppEnvironmentProfile.values.firstWhere(
      (profile) => profile.name == requested,
      orElse: () => throw StateError(
        'Unknown OLLOMI_APP_PROFILE "$requested". Use local_dev or production.',
      ),
    );
  }
}
