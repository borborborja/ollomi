import 'package:omi/pages/settings/local_integrations_page.dart';
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/action_items/widgets/task_selection_action_bar.dart';
import 'package:omi/pages/conversations/widgets/merge_action_bar.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/phone_calls/active_call_banner.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';

import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/integrations/apple_reminders_sync_service.dart';
import 'package:omi/services/quick_actions_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/services/announcement_service.dart';
import 'package:omi/services/account_cutover/account_cutover_blocking_gate.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/analytics/background_resource_telemetry.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';
import 'widgets/battery_info_widget.dart';
import 'widgets/home_capture_bar.dart';

class HomePageWrapper extends StatefulWidget {
  final String? navigateToRoute;
  const HomePageWrapper({super.key, this.navigateToRoute});

  @override
  State<HomePageWrapper> createState() => _HomePageWrapperState();
}

class _HomePageWrapperState extends State<HomePageWrapper> {
  @override
  Widget build(BuildContext context) {
    // Self-gate so onboarding/pushAndRemoveUntil destinations cannot boot
    // product traffic while cutover enforcement is blocking.
    return AccountCutoverBlockingGate(
      productBuilder: (context) => _HomePageProduct(navigateToRoute: widget.navigateToRoute),
    );
  }
}

class _HomePageProduct extends StatefulWidget {
  const _HomePageProduct({this.navigateToRoute});

  final String? navigateToRoute;

  @override
  State<_HomePageProduct> createState() => _HomePageProductState();
}

class _HomePageProductState extends State<_HomePageProduct> {
  String? _navigateToRoute;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Check actual system permission state — the SharedPreferences flag may
      // be stale (e.g. user granted via Settings > Permissions, or reinstall).
      final notifGranted = await Permission.notification.isGranted;
      if (notifGranted) {
        SharedPreferencesUtil().notificationsEnabled = true;
        NotificationService.instance.register();
        NotificationService.instance.saveNotificationToken();
      }
    });
    _navigateToRoute = widget.navigateToRoute;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return HomePage(navigateToRoute: _navigateToRoute);
  }
}

class HomePage extends StatefulWidget {
  final String? navigateToRoute;
  const HomePage({super.key, this.navigateToRoute});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver, TickerProviderStateMixin {
  ForegroundUtil foregroundUtil = ForegroundUtil();

  bool scriptsInProgress = false;
  StreamSubscription? _notificationStreamSubscription;

  final GlobalKey<HomeContentPageState> _homeContentPageKey = GlobalKey<HomeContentPageState>();
  final GlobalKey<State<ConversationsPage>> _conversationsPageKey = GlobalKey<State<ConversationsPage>>();
  final GlobalKey<State<ActionItemsPage>> _actionItemsPageKey = GlobalKey<State<ActionItemsPage>>();
  final GlobalKey<AppsPageState> _appsPageKey = GlobalKey<AppsPageState>();
  // Keep the IndexedStack slots stable, but defer constructing non-selected
  // tabs until the user visits them. Once created, a tab remains in the stack
  // so its scroll position and other state are preserved.
  final List<Widget?> _pages = List<Widget?>.filled(4, null);
  final Set<int> _scheduledPageInitializations = <int>{};

  // Freemium switch handler for auto-switch dialogs
  final FreemiumSwitchHandler _freemiumHandler = FreemiumSwitchHandler();

  late final BackgroundResourceTelemetry _backgroundResourceTelemetry = BackgroundResourceTelemetry(
    emit: (eventName, properties) => PlatformManager.instance.analytics.track(eventName, properties: properties),
  );

  CaptureProvider? _captureProvider;
  CaptureProvider? _captureProviderForQuickActions;

  void _ensurePageInitialized(int pageIndex) {
    if (pageIndex < 0 || pageIndex >= _pages.length || _pages[pageIndex] != null) return;

    switch (pageIndex) {
      case 0:
        _pages[pageIndex] = HomeContentPage(key: _homeContentPageKey);
        break;
      case 1:
        _pages[pageIndex] = ConversationsPage(key: _conversationsPageKey);
        break;
      case 2:
        _pages[pageIndex] = ActionItemsPage(key: _actionItemsPageKey, onAddGoal: _addGoal);
        break;
      case 3:
        _pages[pageIndex] = AppsPage(key: _appsPageKey);
        break;
    }
  }

  void _schedulePageInitialization(int pageIndex) {
    if (pageIndex < 0 || pageIndex >= _pages.length || _pages[pageIndex] != null) return;
    if (!_scheduledPageInitializations.add(pageIndex)) return;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scheduledPageInitializations.remove(pageIndex);
      if (!mounted || _pages[pageIndex] != null) return;
      setState(() => _ensurePageInitialized(pageIndex));
    });
    // addPostFrameCallback does not schedule a frame by itself. Background
    // prewarming often runs while the UI is idle, so explicitly request one.
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _prewarmRemainingTabs(int selectedIndex) {
    var delay = const Duration(milliseconds: 350);
    for (var index = 0; index < _pages.length; index++) {
      if (index == selectedIndex) continue;
      final pageIndex = index;
      Timer(delay, () {
        if (!mounted) return;
        _schedulePageInitialization(pageIndex);
      });
      delay += const Duration(milliseconds: 180);
    }
  }

  List<Widget> _buildPages(int selectedIndex) {
    return [
      for (var index = 0; index < _pages.length; index++)
        TickerMode(
          enabled: index == selectedIndex,
          child: RepaintBoundary(child: _pages[index] ?? _TabLoadingSkeleton(tabIndex: index)),
        ),
    ];
  }

  void _scrollToTop(int pageIndex) {
    switch (pageIndex) {
      case 0:
        _homeContentPageKey.currentState?.scrollToTop();
        break;
      case 1:
        final conversationsState = _conversationsPageKey.currentState;
        if (conversationsState != null) {
          (conversationsState as dynamic).scrollToTop();
        }
        break;
      case 2:
        final actionItemsState = _actionItemsPageKey.currentState;
        if (actionItemsState != null) {
          (actionItemsState as dynamic).scrollToTop();
        }
        break;
      case 3:
        _appsPageKey.currentState?.scrollToTop();
        break;
    }
  }

  void _addGoal() {
    _ensurePageInitialized(1);
    context.read<HomeProvider>().setIndex(1);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final conversationsState = _conversationsPageKey.currentState;
      if (conversationsState != null) {
        (conversationsState as dynamic).addGoal();
      }
    });
  }

  BackgroundResourceSnapshot _captureBackgroundResourceSnapshot({
    CaptureProvider? captureProvider,
    bool foregroundTaskRunning = false,
  }) {
    final capture = captureProvider ?? Provider.of<CaptureProvider>(context, listen: false);
    return BackgroundResourceSnapshot(
      bleBytesReceived: 0,
      websocketBytesSent: capture.lifetimeWsSocketBytesSent,
      recordingState: capture.recordingState.name,
      deviceConnected: false,
      deviceType: 'phone',
      batchModeEnabled: SharedPreferencesUtil().batchModeEnabled,
      foregroundTaskRunning: foregroundTaskRunning,
    );
  }

  Future<BackgroundResourceSnapshot> _loadBackgroundResourceSnapshot(
    DateTime backgroundStartedAt,
    BackgroundResourceSnapshot startSnapshot,
  ) async {
    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
    var foregroundTaskRunning = false;
    try {
      foregroundTaskRunning = await FlutterForegroundTask.isRunningService;
    } catch (_) {}

    return _captureBackgroundResourceSnapshot(
      captureProvider: captureProvider,
      foregroundTaskRunning: foregroundTaskRunning,
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    String event = '';
    if (state == AppLifecycleState.paused) {
      event = 'App is paused';
      if (mounted) {
        _backgroundResourceTelemetry.onPaused(_captureBackgroundResourceSnapshot());
        Provider.of<CaptureProvider>(context, listen: false).setMetricsAppActive(false);
      }
    } else if (state == AppLifecycleState.resumed) {
      event = 'App is resumed';

      // Reload convos
      if (mounted) {
        Provider.of<ConversationProvider>(context, listen: false).refreshConversations();
        final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
        captureProvider.setMetricsAppActive(true);
        unawaited(_backgroundResourceTelemetry.onResumed(_loadBackgroundResourceSnapshot));
        captureProvider.refreshInProgressConversations();
        // Heal phone-mic sessions that went silent while another app played
        // audio (Stage Manager / YouTube) without an AVAudioSession interrupt.
        captureProvider.onAppResumed();
        // Pick up any batch recordings the native layer wrote while backgrounded/closed.
        Provider.of<LocalRecordingsProvider>(context, listen: false).refresh();
      }
      // Sync Apple Reminders on foreground resume
      if (mounted && PlatformService.isApple) {
        final taskProvider = Provider.of<TaskIntegrationProvider>(context, listen: false);
        if (taskProvider.selectedApp == TaskIntegrationApp.appleReminders) {
          AppleRemindersSyncService().syncOnForegroundResume().then((_) {
            if (mounted) {
              Provider.of<ActionItemsProvider>(context, listen: false).forceRefreshActionItems();
            }
          });
        }
      }
    } else if (state == AppLifecycleState.hidden) {
      event = 'App is hidden';
    } else if (state == AppLifecycleState.detached) {
      event = 'App is detached';
    } else {
      return;
    }
    Logger.debug(event);
    PlatformManager.instance.crashReporter.logInfo(event);
  }

  ///Screens with respect to subpage
  final Map<String, Widget> screensWithRespectToPath = {'/facts': const MemoriesPage()};
  bool? previousConnection;

  void _onReceiveTaskData(dynamic data) async {
    if (data is! Map<String, dynamic>) return;
    if (!(data.containsKey('latitude') && data.containsKey('longitude'))) return;
    await updateUserGeolocation(
      geolocation: Geolocation(
        latitude: data['latitude'],
        longitude: data['longitude'],
        accuracy: data['accuracy'],
        altitude: data['altitude'],
        time: DateTime.parse(data['time']).toUtc(),
      ),
    );
  }

  @override
  void initState() {
    SharedPreferencesUtil().onboardingCompleted = true;
    if (!SharedPreferencesUtil().permissionsCompleted) {
      SharedPreferencesUtil().permissionsCompleted = true;
    }
    updateUserOnboardingState(completed: true);

    // Navigate uri
    Uri? navigateToUri;
    var pageAlias = "home";
    var homePageIdx = 0;
    String? detailPageId;

    if (widget.navigateToRoute != null && widget.navigateToRoute!.isNotEmpty) {
      navigateToUri = Uri.tryParse("http://localhost.com${widget.navigateToRoute!}");
      Logger.debug("initState ${navigateToUri?.pathSegments.join("...")}");
      var segments = navigateToUri?.pathSegments ?? [];
      if (segments.isNotEmpty) {
        pageAlias = segments[0];
      }
      if (segments.length > 1) {
        detailPageId = segments[1];
      }

      switch (pageAlias) {
        case "action-items":
          homePageIdx = 2;
          break;
        case "memories":
        case "facts":
          homePageIdx = 0;
          break;
        case "apps":
          homePageIdx = 3;
          break;
      }
    }

    // Home controller
    context.read<HomeProvider>().selectedIndex = homePageIdx;
    _ensurePageInitialized(homePageIdx);
    WidgetsBinding.instance.addObserver(this);
    _prewarmRemainingTabs(homePageIdx);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Android needs a foreground service to keep capture/location work alive.
      // On iOS this plugin boots a second Flutter engine; conversation location
      // is captured directly at recording start and first transcript instead.
      if (Platform.isAndroid) {
        final permission = await Geolocator.checkPermission();
        if (permission == LocationPermission.always || permission == LocationPermission.whileInUse) {
          await ForegroundUtil.initializeForegroundService();
          await ForegroundUtil.startForegroundTask();
        }
      } else if (Platform.isIOS) {
        // Stop a headless foreground-task engine persisted by an older build.
        // Native BLE/audio background modes continue to own active capture.
        await ForegroundUtil.stopForegroundTask();
      }
      if (mounted) {
        await Provider.of<HomeProvider>(context, listen: false).setUserPeople();
      }
      // Navigate
      if (!mounted) return;
      switch (pageAlias) {
        case "apps":
          if (detailPageId != null && detailPageId.isNotEmpty) {
            final appProvider = context.read<AppProvider>();
            var app = await appProvider.getAppFromId(detailPageId);
            if (app != null && mounted) {
              Navigator.push(context, MaterialPageRoute(builder: (context) => AppDetailPage(app: app)));
            }
          }
          break;
        case "chat":
          Logger.debug('inside chat alias $detailPageId');
          if (detailPageId != null && detailPageId.isNotEmpty) {
            var appId = detailPageId != "omi" ? detailPageId : ''; // omi ~ no select
            if (mounted) {
              var appProvider = Provider.of<AppProvider>(context, listen: false);
              var messageProvider = Provider.of<MessageProvider>(context, listen: false);
              App? selectedApp;
              if (appId.isNotEmpty) {
                selectedApp = await appProvider.getAppFromId(appId);
              }
              appProvider.setSelectedChatAppId(appId);
              await messageProvider.refreshMessages();
              if (messageProvider.messages.isEmpty) {
                messageProvider.sendInitialAppMessage(selectedApp);
              }
            }
          } else {
            if (mounted) {
              await Provider.of<MessageProvider>(context, listen: false).refreshMessages();
            }
          }
          // Navigate to chat page directly since it's no longer in the tab bar
          // All async setup (streamDeviceRecording, refreshMessages) is already awaited above,
          // so the widget tree is fully settled — push directly.
          if (mounted) {
            Navigator.push(context, MaterialPageRoute(builder: (context) => const ChatPage(isPivotBottom: false)));
          }
          break;
        case "settings":
          // Use context from the current widget instead of navigator key for bottom sheet
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              SettingsDrawer.show(context);
            }
          });
          if (detailPageId == 'data-privacy') {
            globalNavigatorKey.currentState?.push(MaterialPageRoute(builder: (context) => const DataPrivacyPage()));
          }
          break;
        case "memories":
        case "facts":
          globalNavigatorKey.currentState?.push(MaterialPageRoute(builder: (context) => const MemoriesPage()));
          break;
        case "conversation":
          // Handle conversation deep link: /conversation/{id}?share=1
          if (detailPageId != null && detailPageId.isNotEmpty) {
            // Check for share query param
            final shouldOpenShare = navigateToUri?.queryParameters['share'] == '1';
            final conversationId = detailPageId; // Capture non-null value

            WidgetsBinding.instance.addPostFrameCallback((_) async {
              if (!mounted) return;

              // Fetch conversation from server
              final conversation = await getConversationById(conversationId);
              if (conversation != null && mounted) {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) =>
                        ConversationDetailPage(conversation: conversation, openShareToContactsOnLoad: shouldOpenShare),
                  ),
                );
              } else {
                Logger.debug('Conversation not found: $conversationId');
              }
            });
          }
          break;
        case "daily-summary":
          if (detailPageId != null && detailPageId.isNotEmpty) {
            // Track notification opened
            PlatformManager.instance.analytics.dailySummaryNotificationOpened(
              summaryId: detailPageId,
              date: '', // Date not available in navigate_to, will be fetched when detail page loads
            );

            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => DailySummaryDetailPage(summaryId: detailPageId!)),
                );
              }
            });
          }
          break;
        case "wrapped":
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(context, MaterialPageRoute(builder: (context) => const Wrapped2025Page()));
            }
          });
          break;
        case "action-items":
          // Tab index already set to 2 (ActionItemsPage) above
          break;
        default:
      }
    });

    _listenToMessagesFromNotification();
    _listenToFreemiumThreshold();
    _checkForAnnouncements();
    _initQuickActions();
    super.initState();

    // After init
    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
  }

  void _checkForAnnouncements() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;

      await Future.delayed(const Duration(seconds: 2));

      if (!mounted) return;

      final announcementProvider = Provider.of<AnnouncementProvider>(context, listen: false);
      await AnnouncementService().checkAndShowAnnouncements(
        context,
        announcementProvider,
        connectedDevice: null,
      );
    });
  }

  void _initQuickActions() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      QuickActionsService.instance.initialize(context);
      _captureProviderForQuickActions = Provider.of<CaptureProvider>(context, listen: false);
      _captureProviderForQuickActions!.addListener(_onDeviceStateChangedForQuickActions);
    });
  }

  void _onDeviceStateChangedForQuickActions() {
    if (!mounted) return;
    QuickActionsService.instance.updateShortcuts(context);
  }

  void _listenToFreemiumThreshold() {
    // Listen to capture provider for freemium threshold events
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      _captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      _captureProvider!.addListener(_onCaptureProviderChanged);
      // Connect freemium session reset callback
      _captureProvider!.onFreemiumSessionReset = () {
        _freemiumHandler.resetDialogFlag();
      };
    });
  }

  void _onCaptureProviderChanged() {
    if (!mounted || _captureProvider == null) return;

    if (!context.read<UsageProvider>().showSubscriptionUI) return;

    _freemiumHandler.checkAndShowDialog(context, _captureProvider!).catchError((e) {
      Logger.debug('[Freemium] Error checking dialog: $e');
      return false;
    });
  }

  void _listenToMessagesFromNotification() {
    _notificationStreamSubscription = NotificationService.instance.listenForServerMessages.listen((message) {
      if (mounted) {
        var selectedApp = Provider.of<AppProvider>(context, listen: false).getSelectedApp();
        if (selectedApp == null || message.appId == selectedApp.id) {
          Provider.of<MessageProvider>(context, listen: false).addMessage(message);
        }
        // chatPageKey.currentState?.scrollToBottom();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      child: Consumer<ConnectivityProvider>(
        builder: (ctx, connectivityProvider, child) {
          bool isConnected = connectivityProvider.isConnected;
          previousConnection ??= true;

          if (previousConnection != isConnected &&
              connectivityProvider.isInitialized &&
              connectivityProvider.previousConnection != isConnected) {
            previousConnection = isConnected;
            if (isConnected) {
              Future.delayed(Duration.zero, () {
                WidgetsBinding.instance.addPostFrameCallback((_) async {
                  if (!mounted) return;

                  final convoProvider = ctx.read<ConversationProvider>();
                  final messageProvider = ctx.read<MessageProvider>();

                  if (convoProvider.conversations.isEmpty) {
                    await convoProvider.getInitialConversations();
                  } else {
                    // Force refresh when internet connection is restored
                    await convoProvider.forceRefreshConversations();
                  }

                  if (messageProvider.messages.isEmpty) {
                    await messageProvider.refreshMessages();
                  }
                });
              });
            }
          }
          return child!;
        },
        child: Selector<HomeProvider, int>(
          selector: (_, homeProvider) => homeProvider.selectedIndex,
          builder: (context, selectedIndex, _) {
            return Scaffold(
              backgroundColor: Theme.of(context).colorScheme.primary,
              resizeToAvoidBottomInset: false,
              appBar: selectedIndex == 5 ? null : _buildAppBar(context),
              body: GestureDetector(
                onTap: () {
                  primaryFocus?.unfocus();
                  // context.read<HomeProvider>().memoryFieldFocusNode.unfocus();
                  // context.read<HomeProvider>().chatFieldFocusNode.unfocus();
                },
                child: Stack(
                  children: [
                    Column(
                      children: [
                        // Show slim green call bar on non-home/conversations tabs when a call is active
                        if (selectedIndex > 1) const ActiveCallTopBar(),
                        if (selectedIndex == 0) const HomeCaptureBar(),
                        Expanded(
                          child: IndexedStack(index: selectedIndex, children: _buildPages(selectedIndex)),
                        ),
                      ],
                    ),
                    Consumer<HomeProvider>(
                      builder: (context, home, child) {
                        if (home.isChatFieldFocused ||
                            home.isAppsSearchFieldFocused ||
                            home.isMemoriesSearchFieldFocused) {
                          return const SizedBox.shrink();
                        }

                        return Stack(
                          children: [
                            BottomNavBar(
                              // Queue page construction after the current
                              // gesture frame. Building a destination directly
                              // in onTapDown makes the tap itself feel stuck.
                              onTabWarmup: _schedulePageInitialization,
                              onTabTap: (index, isRepeat) {
                                if (isRepeat) {
                                  _scrollToTop(index);
                                } else {
                                  // When tapping Conversations directly, reset to conversations view
                                  if (index == 1) {
                                    final cp = context.read<ConversationProvider>();
                                    if (cp.showDailySummaries) cp.toggleDailySummaries();
                                  }
                                  // Change tabs immediately. If background
                                  // prewarming has not completed yet, the
                                  // destination paints a skeleton for one frame
                                  // and mounts its real content afterwards.
                                  home.setIndex(index);
                                  _schedulePageInitialization(index);
                                }
                              },
                            ),
                            if (home.selectedIndex == 0)
                              Positioned(
                                left: 16,
                                right: 16,
                                // Derived from the nav row's own geometry so the
                                // two cannot drift: changing the row's height or
                                // the inset it reserves moves this with it,
                                // instead of silently closing the gap.
                                bottom: kBottomNavBarHeight - kBottomNavChatBarGap + bottomNavBarReservedInset(context),
                                child: Row(
                                  children: [
                                    Expanded(child: _buildChatBar(context)),
                                    const SizedBox(width: 10),
                                    const HomeRecordButton(),
                                  ],
                                ),
                              ),
                          ],
                        );
                      },
                    ),
                    // Merge action bar - floats above bottom nav when in selection mode
                    if (selectedIndex == 1) const Positioned(left: 0, right: 0, bottom: 0, child: MergeActionBar()),
                    // Task selection action bar - floats above bottom nav on the
                    // tasks tab when selection mode is active in ActionItemsProvider.
                    if (selectedIndex == 2)
                      const Positioned(left: 0, right: 0, bottom: 0, child: TaskSelectionActionBar()),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildChatBar(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        PlatformManager.instance.analytics.bottomNavigationTabClicked('Chat');
        Navigator.push(context,
            MaterialPageRoute(fullscreenDialog: true, builder: (context) => const ChatPage(isPivotBottom: false)));
      },
      child: Container(
        height: 62,
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(32),
          border: Border.all(color: const Color(0xFF35343B), width: 1),
        ),
        child: Row(
          children: [
            const SizedBox(width: 18),
            Expanded(
              child: Text(
                context.l10n.askOmi,
                style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            GestureDetector(
              onTap: () {
                HapticFeedback.lightImpact();
                PlatformManager.instance.analytics.bottomNavigationTabClicked('Chat Voice');
                Navigator.push(
                  context,
                  MaterialPageRoute(
                      fullscreenDialog: true,
                      builder: (context) => const ChatPage(isPivotBottom: false, autoStartVoice: true)),
                );
              },
              child: Container(
                width: 42,
                height: 42,
                margin: const EdgeInsets.only(right: 6),
                alignment: Alignment.center,
                decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                child: const FaIcon(FontAwesomeIcons.microphone, size: 15, color: Colors.black),
              ),
            ),
          ],
        ),
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: Theme.of(context).colorScheme.surface,
      title: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Keep the hardware entry point visible even though Ollomi's local
          // onboarding no longer requires a wearable. Without this, the
          // pairing page is unreachable until a device has already been
          // paired, which prevents first-time Omi/Friend connections.
          const BatteryInfoWidget(),
          Row(
            children: [
              // Search and Calendar buttons - only on home page
              Consumer2<HomeProvider, ConversationProvider>(
                builder: (context, homeProvider, convoProvider, _) {
                  // Only show search and calendar buttons on Conversations tab (index 1)
                  if (homeProvider.selectedIndex != 1) {
                    return const SizedBox.shrink();
                  }

                  // Hide search button if there's an active search query
                  bool shouldShowSearchButton = convoProvider.previousQuery.isEmpty;
                  return Row(
                    children: [
                      // Search button - show when no active search, clicking closes search bar
                      if (shouldShowSearchButton)
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: homeProvider.showConvoSearchBar
                                ? Colors.deepPurple.withValues(alpha: 0.5)
                                : const Color(0xFF1F1F25),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            icon: const Icon(Icons.search, size: 18, color: Colors.white70),
                            onPressed: () {
                              HapticFeedback.mediumImpact();
                              homeProvider.toggleConvoSearchBar();
                            },
                          ),
                        ),
                      // Calendar button - only show when date filter is active
                      if (convoProvider.selectedStartDate != null) ...[
                        const SizedBox(width: 8),
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: Colors.deepPurple.withValues(alpha: 0.5),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            icon: const FaIcon(FontAwesomeIcons.calendarDay, size: 16, color: Colors.white),
                            onPressed: () async {
                              HapticFeedback.mediumImpact();
                              await showConversationDateRangePicker(context);
                            },
                          ),
                        ),
                      ],
                      const SizedBox(width: 8),
                    ],
                  );
                },
              ),
              // Tasks page buttons - export and completed toggle
              Consumer2<HomeProvider, ActionItemsProvider>(
                builder: (context, homeProvider, actionItemsProvider, _) {
                  if (homeProvider.selectedIndex != 2) {
                    return const SizedBox.shrink();
                  }
                  final showCompleted = actionItemsProvider.showCompletedView;
                  return Row(
                    children: [
                      // Export button
                      Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16, color: Colors.white70),
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            PlatformManager.instance.analytics.exportTasksBannerClicked();
                            Navigator.of(
                              context,
                            ).push(MaterialPageRoute(builder: (context) => const LocalIntegrationsPage()));
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                      // Completed toggle
                      Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: showCompleted ? Colors.deepPurple.withValues(alpha: 0.5) : const Color(0xFF1F1F25),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          icon: FaIcon(
                            FontAwesomeIcons.solidCircleCheck,
                            size: 16,
                            color: showCompleted ? Colors.white : Colors.white70,
                          ),
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            actionItemsProvider.toggleShowCompletedView();
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                    ],
                  );
                },
              ),
              // Apps tab — Create app pull-down menu (shown only on Apps tab, left of settings)
              Consumer<HomeProvider>(
                builder: (context, homeProvider, _) {
                  if (homeProvider.selectedIndex != 3) return const SizedBox.shrink();
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: PullDownButton(
                      itemBuilder: (context) => [
                        PullDownMenuItem(
                          title: context.l10n.createAnApp,
                          subtitle: context.l10n.createAndShareYourApp,
                          iconWidget: const Icon(Icons.apps, size: 18),
                          onTap: () {
                            PlatformManager.instance.analytics.pageOpened('Submit App');
                            routeToPage(context, const LocalIntegrationsPage());
                          },
                        ),
                        PullDownMenuItem(
                          title: context.l10n.addMcpServer,
                          subtitle: context.l10n.connectExternalAiTools,
                          iconWidget: const Icon(Icons.cable, size: 18),
                          onTap: () {
                            PlatformManager.instance.analytics.pageOpened('Add MCP Server');
                            routeToPage(context, const LocalIntegrationsPage());
                          },
                        ),
                      ],
                      buttonBuilder: (context, showMenu) => GestureDetector(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          showMenu();
                        },
                        child: Container(
                          width: 36,
                          height: 36,
                          decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
                          child: const Icon(Icons.add, size: 18, color: Colors.white70),
                        ),
                      ),
                    ),
                  );
                },
              ),
              // Settings button - always visible
              Container(
                width: 36,
                height: 36,
                decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
                child: IconButton(
                  padding: EdgeInsets.zero,
                  icon: const FaIcon(FontAwesomeIcons.gear, size: 16, color: Colors.white70),
                  onPressed: () {
                    HapticFeedback.mediumImpact();
                    PlatformManager.instance.analytics.pageOpened('Settings');
                    String language = SharedPreferencesUtil().userPrimaryLanguage;
                    bool hasSpeech = SharedPreferencesUtil().hasSpeakerProfile;
                    String transcriptModel = SharedPreferencesUtil().transcriptionModel;
                    SettingsDrawer.show(context);
                    if (language != SharedPreferencesUtil().userPrimaryLanguage ||
                        hasSpeech != SharedPreferencesUtil().hasSpeakerProfile ||
                        transcriptModel != SharedPreferencesUtil().transcriptionModel) {
                      if (context.mounted) {
                        context.read<CaptureProvider>().onRecordProfileSettingChanged();
                      }
                    }
                  },
                ),
              ),
            ],
          ),
        ],
      ),
      elevation: 0,
      centerTitle: true,
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    // Cancel stream subscription to prevent memory leak
    _notificationStreamSubscription?.cancel();
    // Remove capture provider listener using stored reference
    if (_captureProvider != null) {
      _captureProvider!.removeListener(_onCaptureProviderChanged);
      _captureProvider!.onFreemiumSessionReset = null;
      _captureProvider = null;
    }
    _captureProviderForQuickActions?.removeListener(_onDeviceStateChangedForQuickActions);
    _captureProviderForQuickActions = null;
    QuickActionsService.instance.reset();
    // Clean up freemium handler
    _freemiumHandler.dispose();
    // Remove foreground task callback to prevent memory leak
    FlutterForegroundTask.removeTaskDataCallback(_onReceiveTaskData);
    if (Platform.isAndroid) {
      ForegroundUtil.stopForegroundTask();
    }
    super.dispose();
  }
}

class _TabLoadingSkeleton extends StatelessWidget {
  const _TabLoadingSkeleton({required this.tabIndex});

  final int tabIndex;

  @override
  Widget build(BuildContext context) {
    final itemCount = tabIndex == 3 ? 6 : 5;
    return IgnorePointer(
      child: ListView.builder(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 120),
        itemCount: itemCount,
        itemBuilder: (context, index) => Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: ShimmerWithTimeout(
            baseColor: const Color(0xFF1F1F25),
            highlightColor: const Color(0xFF303038),
            child: Container(
              height: index == 0 ? 34 : 76,
              width: double.infinity,
              decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(18)),
            ),
          ),
        ),
      ),
    );
  }
}
