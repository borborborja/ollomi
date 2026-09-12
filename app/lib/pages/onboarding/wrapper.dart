import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/primary_language/primary_language_widget.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/auth_service.dart';

/// Local onboarding needs no pendant, biometric enrollment or cloud graph.
class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key, this.forceAuthPage = false});
  final bool forceAuthPage;

  @override
  State<OnboardingWrapper> createState() => _OnboardingWrapperState();
}

class _OnboardingWrapperState extends State<OnboardingWrapper> {
  int _step = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && !widget.forceAuthPage && AuthService.instance.isSignedIn()) {
        _afterLogin();
      }
    });
  }

  void _goHome() {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const HomePageWrapper()),
      (route) => false,
    );
  }

  void _afterLogin() {
    if (!mounted) return;
    context.read<UsageProvider>().fetchSubscription();
    if (!SharedPreferencesUtil().aiConsentGiven) {
      setState(() => _step = 1);
    } else if (!SharedPreferencesUtil().onboardingCompleted) {
      setState(() => _step = 2);
    } else if (!SharedPreferencesUtil().permissionsCompleted) {
      setState(() => _step = 4);
    } else {
      _goHome();
    }
  }

  void _complete() {
    SharedPreferencesUtil().onboardingCompleted = true;
    SharedPreferencesUtil().permissionsCompleted = true;
    updateUserOnboardingState(completed: true);
    _goHome();
  }

  @override
  Widget build(BuildContext context) {
    final Widget page;
    switch (_step) {
      case 0:
        page = AuthComponent(onSignIn: _afterLogin);
      case 1:
        page = AiConsentWidget(onAgree: () {
          SharedPreferencesUtil().aiConsentGiven = true;
          _afterLogin();
        });
      case 2:
        page = NameWidget(goNext: () => setState(() => _step = 3));
      case 3:
        page = PrimaryLanguageWidget(goNext: () => setState(() => _step = 4));
      default:
        page = PermissionsWidget(goNext: _complete);
    }
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Stack(children: [
          Positioned.fill(
            child: Image.asset(Assets.images.onboardingBg2.path,
                fit: BoxFit.cover,
                cacheWidth: (MediaQuery.sizeOf(context).width * MediaQuery.devicePixelRatioOf(context)).round()),
          ),
          page,
          if (_step >= 2)
            SafeArea(
                child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                if (_step > 2)
                  IconButton(
                      key: const Key('onboarding-back'),
                      onPressed: () => setState(() => _step -= 1),
                      icon: const Icon(Icons.arrow_back, color: Colors.white)),
                ...List.generate(
                    3,
                    (index) => Container(
                          margin: const EdgeInsets.symmetric(horizontal: 4),
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                              shape: BoxShape.circle, color: index <= _step - 2 ? Colors.white : Colors.grey),
                        )),
              ]),
            )),
        ]),
      ),
    );
  }
}
