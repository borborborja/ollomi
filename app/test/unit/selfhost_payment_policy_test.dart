import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/usage_provider.dart';

void main() {
  test('self-hosted billing operations are inert', () async {
    final provider = UsageProvider();

    expect(provider.showSubscriptionUI, isFalse);
    expect(provider.isOutOfCredits, isFalse);
    expect(provider.canAccessPhoneCalls, isTrue);
    await provider.loadAvailablePlans();
    expect(provider.availablePlans, isNull);
    expect(await provider.cancelUserSubscription(), isFalse);
    expect(await provider.upgradeUserSubscription(priceId: 'legacy-price'), isNull);
    expect(await provider.createUserCheckoutSession(priceId: 'legacy-price'), isNull);
    expect(await provider.openCustomerPortal(), isNull);
  });
}
