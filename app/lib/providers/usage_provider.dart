import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/utils/logger.dart';

class UsageProvider with ChangeNotifier {
  UserSubscriptionResponse? _subscription;
  UserSubscriptionResponse? get subscription => _subscription;

  /// Ollomi is self-hosted and deliberately has no paid plan surface.
  bool get showSubscriptionUI => false;
  UsageStats? _todayUsage;
  UsageStats? get todayUsage => _todayUsage;

  UsageStats? _monthlyUsage;
  UsageStats? get monthlyUsage => _monthlyUsage;

  UsageStats? _yearlyUsage;
  UsageStats? get yearlyUsage => _yearlyUsage;

  UsageStats? _allTimeUsage;
  UsageStats? get allTimeUsage => _allTimeUsage;

  List<UsageHistoryPoint>? _todayHistory;
  List<UsageHistoryPoint>? get todayHistory => _todayHistory;

  List<UsageHistoryPoint>? _monthlyHistory;
  List<UsageHistoryPoint>? get monthlyHistory => _monthlyHistory;

  List<UsageHistoryPoint>? _yearlyHistory;
  List<UsageHistoryPoint>? get yearlyHistory => _yearlyHistory;

  List<UsageHistoryPoint>? _allTimeHistory;
  List<UsageHistoryPoint>? get allTimeHistory => _allTimeHistory;

  bool _isUsageLoading = false;
  bool _isSubscriptionLoading = false;
  bool _isPaymentLoading = false;
  bool get isLoading => _isUsageLoading || _isSubscriptionLoading || _isPaymentLoading;

  String? _error;
  String? get error => _error;

  bool _forceOutOfCredits = false;

  /// Bumped on [clearUserData] so responses from a previous session's
  /// in-flight fetches are discarded instead of repopulating cleared state.
  int _sessionGeneration = 0;

  // Chat quota derived from subscription response
  double get chatQuotaUsed => _subscription?.chatQuotaUsed ?? 0.0;
  String? get chatQuotaUnit => _subscription?.chatQuotaUnit;
  double get chatQuotaPercent => _subscription?.chatQuotaPercent ?? 0.0;
  bool get chatQuotaAllowed => _subscription?.chatQuotaAllowed ?? true;

  // Phone call feature — derived from subscription response. Only consult
  // the server-driven quota when the user is on the free tier or the
  // subscription UI is hidden; paid users with the paywall visible skip
  // straight to the existing unlimited behavior.
  PhoneCallQuota? get phoneCallQuota => _subscription?.phoneCallQuota;

  /// Device and OS support determine whether calls work; there is no payment
  /// gate in a self-hosted installation.
  bool get canAccessPhoneCalls => true;
  bool get shouldShowPhoneCallsEntry => true;

  // Payment-related state
  Map<String, dynamic>? _availablePlans;
  Map<String, dynamic>? get availablePlans => _availablePlans;
  bool _isLoadingPlans = false;
  bool get isLoadingPlans => _isLoadingPlans;

  bool get isOutOfCredits => false;

  @visibleForTesting
  void debugSetSubscription(UserSubscriptionResponse? value) {
    _subscription = value;
    TranscriptionAllowanceCache.replace(value?.transcriptionAllowance);
    notifyListeners();
  }

  /// Wipes user-scoped state on logout so the next account doesn't inherit
  /// the previous account's subscription/usage (e.g. a stale Pro badge).
  void clearUserData() {
    TranscriptionAllowanceCache.clear();
    _subscription = null;
    _todayUsage = null;
    _monthlyUsage = null;
    _yearlyUsage = null;
    _allTimeUsage = null;
    _todayHistory = null;
    _monthlyHistory = null;
    _yearlyHistory = null;
    _allTimeHistory = null;
    _availablePlans = null;
    _forceOutOfCredits = false;
    _error = null;
    _sessionGeneration++;
    _isSubscriptionLoading = false;
    _isUsageLoading = false;
    _isPaymentLoading = false;
    _isLoadingPlans = false;
    notifyListeners();
  }

  Future<void> markAsOutOfCreditsAndRefresh() async {}

  Future<void> fetchSubscription() async {
    // Do not call the upstream subscription endpoint: Ollomi has neither
    // billing nor transcription credit limits. Keeping this method makes the
    // retained capture lifecycle harmless while Kotlin migration is pending.
    if (_subscription == null && !_forceOutOfCredits) return;
    _subscription = null;
    _forceOutOfCredits = false;
    TranscriptionAllowanceCache.clear();
    notifyListeners();
  }

  /// Alias for fetchSubscription - refreshes subscription data from backend
  Future<void> refreshSubscription() => fetchSubscription();

  Future<void> fetchUsageStats({required String period}) async {
    if (_isUsageLoading) return;

    final generation = _sessionGeneration;
    _isUsageLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await getUserUsage(period: period);
      if (generation != _sessionGeneration) return; // Session cleared mid-flight; discard stale response.
      if (response != null) {
        switch (period) {
          case 'today':
            _todayUsage = response.today;
            _todayHistory = response.history;
            break;
          case 'monthly':
            _monthlyUsage = response.monthly;
            _monthlyHistory = response.history;
            break;
          case 'yearly':
            _yearlyUsage = response.yearly;
            _yearlyHistory = response.history;
            break;
          case 'all_time':
            _allTimeUsage = response.allTime;
            _allTimeHistory = response.history;
            break;
        }
      } else {
        _error = 'Failed to load usage data. Please try again later.';
      }
    } catch (e) {
      if (generation != _sessionGeneration) return;
      _error = 'Failed to load usage data. Please try again later.';
      Logger.debug('Failed to fetch usage stats: $e');
    } finally {
      if (generation == _sessionGeneration) {
        _isUsageLoading = false;
        notifyListeners();
      }
    }
  }

  // Compatibility no-ops for legacy widgets that will disappear with the
  // Kotlin UI migration. They must never contact an upstream billing API.
  Future<void> loadAvailablePlans() async {
    _availablePlans = null;
    _isLoadingPlans = false;
    notifyListeners();
  }

  Future<bool> cancelUserSubscription({String? reason, String? reasonDetails}) async => false;

  Future<Map<String, dynamic>?> upgradeUserSubscription({required String priceId, String? promotionCode}) async => null;

  Future<Map<String, dynamic>?> createUserCheckoutSession({required String priceId, String? promotionCode}) async =>
      null;

  Future<Map<String, String>?> openCustomerPortal() async => null;
}
