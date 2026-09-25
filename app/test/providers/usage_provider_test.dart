import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';

UserSubscriptionResponse _proSubscription() {
  return UserSubscriptionResponse(
    subscription: Subscription(plan: PlanType.unlimited, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  );
}

UserSubscriptionResponse _subscriptionOn(PlanType plan, {required int used, required int limit}) {
  return UserSubscriptionResponse(
    subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: used,
    transcriptionSecondsLimit: limit,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  );
}

void main() {
  // The self-hosted fork removed billing: there is no paid plan surface, no
  // transcription credit limit and no payment gate on phone calls (see
  // `selfhost_payment_policy_test.dart`). These tests pin that policy instead of
  // the upstream Omi tier matrix, so a reintroduced plan gate fails here.
  group('UsageProvider.clearUserData', () {
    test('resets subscription state so the next login cannot inherit the previous account plan', () {
      final provider = UsageProvider();
      provider.debugSetSubscription(_proSubscription());
      expect(provider.subscription, isNotNull);

      var notified = false;
      provider.addListener(() => notified = true);
      provider.clearUserData();

      expect(provider.subscription, isNull);
      expect(provider.isOutOfCredits, isFalse);
      expect(provider.error, isNull);
      expect(notified, isTrue);
    });
  });

  group('UsageProvider is unmetered on a self-hosted server', () {
    test('no plan ever runs out of credits', () {
      final provider = UsageProvider();
      for (final plan in [
        PlanType.plus,
        PlanType.unlimited,
        PlanType.unlimitedV2,
        PlanType.unknown('future_plan_123'),
      ]) {
        provider.debugSetSubscription(_subscriptionOn(plan, used: 90000, limit: 90000));
        expect(provider.isOutOfCredits, isFalse, reason: '${plan.name} must stay unmetered');
      }
    });

    test('phone calls are available regardless of plan', () {
      final provider = UsageProvider();
      for (final plan in [PlanType.plus, PlanType.unlimitedV2, PlanType.unknown('future_plan_123')]) {
        provider.debugSetSubscription(_subscriptionOn(plan, used: 0, limit: 0));
        expect(provider.canAccessPhoneCalls, isTrue, reason: '${plan.name} must not be gated');
      }
    });

    test('the subscription UI stays hidden', () {
      expect(UsageProvider().showSubscriptionUI, isFalse);
    });
  });
}
