import 'package:omi/app_globals.dart';
import 'package:omi/utils/auth/clear_user_state.dart';
import 'dart:async';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';

class AuthenticationProvider extends BaseProvider {
  AuthUserSnapshot? user = AuthService.instance.currentUser;
  String? authToken;
  bool requiresReauthentication = false;
  int sessionExpirationGeneration = 0;
  StreamSubscription? _userSubscription;
  StreamSubscription? _expirationSubscription;
  AuthenticationProvider({bool initializeListeners = true}) {
    if (!initializeListeners) return;
    _userSubscription = AuthService.instance.authStateChanges.listen((value) {
      user = value;
      final context = globalNavigatorKey.currentContext;
      if (value == null && context != null && context.mounted) clearAllUserState(context);
      requiresReauthentication = value == null;
      unawaited(AccountCutoverRuntime.instance.bindAuthenticatedOwner(value?.uid));
      notifyListeners();
    });
    _expirationSubscription = AuthService.instance.sessionExpiredEvents.listen((event) {
      requiresReauthentication = true;
      sessionExpirationGeneration++;
      notifyListeners();
    });
  }
  void openPrivacyPolicy() { launchUrl(Uri.parse('${AuthService.instance.serverUrl}privacy')); }
  void openTermsOfService() => openPrivacyPolicy();
  bool isSignedIn() => AuthService.instance.isSignedIn() && !requiresReauthentication;
  Future<void> signIn(String server, String email, String password, void Function() onSignIn) async {
    setLoadingState(true);
    try {
      await AuthService.instance.signIn(server, email, password);
      user = AuthService.instance.currentUser;
      requiresReauthentication = false;
      onSignIn();
    } finally { setLoadingState(false); }
  }
  @override void dispose() {
    _userSubscription?.cancel();
    _expirationSubscription?.cancel();
    super.dispose();
  }
}
