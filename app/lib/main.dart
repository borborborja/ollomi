import 'package:omi/services/local_audio_share.dart';
import 'dart:async';
import 'dart:ui';
// trigger rebuild

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:marionette_flutter/marionette_flutter.dart';

import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:provider/provider.dart';
import 'package:talker_flutter/talker_flutter.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/coordinators/provider_capture_external_actions.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/mobile/authenticated_product_scope.dart';
import 'package:omi/env/env.dart';

import 'package:omi/flavors.dart';

import 'package:omi/startup_failure_app.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/notifications.dart';

import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/analytics/app_session_telemetry.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/debugging/local_diagnostics.dart';

import 'package:omi/utils/analytics/rage_click_context_tracker.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/notification_channel_strings.dart';

Future _init() async {
  await SharedPreferencesUtil.init();
  await AuthService.instance.initialize();

  FlutterForegroundTask.initCommunicationPort();

  // Service manager
  await ServiceManager.init();

  await PlatformManager.initializeServices();
  await NotificationChannelStrings.loadAppLocale();
  await NotificationService.instance.initialize();

  final isAuth = AuthService.instance.isSignedIn();
  if (isAuth) {
    await AccountCutoverRuntime.instance.bindAuthenticatedOwner(AuthService.instance.currentUser?.uid);
  }
  initOpus(await opus_flutter.load());

  // Route native Omi/Friend BLE events into the Dart device service before it
  // starts restoring or connecting a persisted device.
  BleFlutterApi.setUp(BleBridge.instance);
  BleBridge.instance.stateRestoredCallback = (peripheralUuids) {
    Logger.debug('main: restored ${peripheralUuids.length} BLE peripherals');
  };

  await LocalDiagnostics.init();
  if (isAuth) {
    PlatformManager.instance.crashReporter.identifyUser(
      AuthService.instance.currentUser?.email ?? '',
      SharedPreferencesUtil().fullName,
      SharedPreferencesUtil().uid,
    );
  }
  FlutterError.onError = (FlutterErrorDetails details) {
    Logger.handle(details.exception, details.stack);
  };

  PlatformDispatcher.instance.onError = (error, stack) {
    Logger.handle(error, stack);
    return true;
  };

  await ServiceManager.instance().start();
  return;
}

void main() {
  runZonedGuarded(
    () async {
      // Ensure
      if (kDebugMode) {
        MarionetteBinding.ensureInitialized();
      } else {
        WidgetsFlutterBinding.ensureInitialized();
      }
      try {
        await _init();
      } catch (error, stack) {
        // Startup failed before the first frame. Without this the launch
        // storyboard stays on screen forever: runApp() is never reached, and the
        // zone handler below only calls debugPrint, which goes nowhere in
        // profile/release builds. A misconfigured OMI_API_BASE_URL cost about a
        // day of investigation for exactly this reason — the app looked hung
        // when it had in fact thrown a precise, actionable StateError.
        {
          Logger.handle(error, stack);
        }
        runApp(StartupFailureApp(error: error, stack: stack));
        return;
      }
      runApp(const MyApp());
    },
    (error, stack) {
      debugPrint('Uncaught error: $error\n$stack');
      {
        Logger.handle(error, stack);
      }
    },
  );
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();

  static _MyAppState of(BuildContext context) => context.findAncestorStateOfType<_MyAppState>()!;

  // The navigator key is necessary to navigate using static methods
  // Delegates to the extracted globalNavigatorKey so files don't need to import main.dart
  static GlobalKey<NavigatorState> get navigatorKey => globalNavigatorKey;
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  final AppSessionTelemetry _appSessionTelemetry = AppSessionTelemetry();

  @override
  void initState() {
    LocalAudioShare.initialize();
    NotificationUtil.initializeNotificationsEventListeners();
    NotificationUtil.initializeIsolateReceivePort();
    WidgetsBinding.instance.addObserver(this);
    _appSessionTelemetry.recordColdStart();
    if (SharedPreferencesUtil().devLogsToFileEnabled) {
      DebugLogManager.setEnabled(true);
    }

    super.initState();
  }

  void _deinit() {
    Logger.debug("App > _deinit");
    ServiceManager.instance().deinit();
    ApiClient.dispose();
  }

  Future<void> _refreshAccountCutoverThenWakeUploads() async {
    if (!AuthService.instance.isSignedIn()) {
      await AccountCutoverRuntime.instance.bindAuthenticatedOwner(null);
      return;
    }
    // Apply fresh cutover control before waking WAL recovery so a stale
    // legacy/allow projection cannot admit one offline upload.
    final resumeUser = AuthService.instance.currentUser;
    final resumeOwner = (resumeUser != null && true) ? resumeUser.uid : null;
    await AccountCutoverRuntime.instance.bindAuthenticatedOwner(resumeOwner);
    SyncReconciler.instance.onForeground();
    unawaited(SyncUploadGate.instance.reconcileFairUseStatus());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    if (state == AppLifecycleState.resumed) {
      _appSessionTelemetry.recordResumed();
      unawaited(_refreshAccountCutoverThenWakeUploads());
    } else if (state == AppLifecycleState.paused) {
      _appSessionTelemetry.recordBackgrounded();
      SyncReconciler.instance.onBackground();
      _onAppPaused();
    } else if (state == AppLifecycleState.detached) {
      _deinit();
    }
  }

  void _onAppPaused() {
    imageCache.clear();
    imageCache.clearLiveImages();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ListenableProvider(create: (context) => ConnectivityProvider()),
        ChangeNotifierProvider(create: (context) => AuthenticationProvider()),
        ChangeNotifierProvider(
          create: (context) {
            final provider = ConversationProvider(localSegmentStore: LocalSegmentStore.appSupport());
            unawaited(provider.hydratePendingDrafts());
            return provider;
          },
        ),
        ListenableProvider(create: (context) => AppProvider()),
        ChangeNotifierProvider(create: (context) => PeopleProvider()),
        ChangeNotifierProvider(create: (context) => UsageProvider()),
        ChangeNotifierProxyProvider<AppProvider, MessageProvider>(
          create: (context) => MessageProvider(),
          update: (BuildContext context, value, MessageProvider? previous) =>
              (previous?..updateAppProvider(value)) ?? MessageProvider(),
        ),
        ChangeNotifierProxyProvider4<ConversationProvider, MessageProvider, PeopleProvider, UsageProvider,
            CaptureProvider>(
          create: (context) => CaptureProvider(localSegmentStore: LocalSegmentStore.appSupport()),
          update: (BuildContext context, conversation, message, people, usage, CaptureProvider? previous) {
            final externalActions = ProviderCaptureExternalActions(
              conversationProvider: conversation,
              messageProvider: message,
              peopleProvider: people,
              usageProvider: usage,
            );
            return (previous?..updateExternalActions(externalActions)) ??
                CaptureProvider(externalActions: externalActions, localSegmentStore: LocalSegmentStore.appSupport());
          },
        ),
        ChangeNotifierProxyProvider<ConversationProvider, LocalRecordingsProvider>(
          create: (context) => LocalRecordingsProvider(),
          update: (BuildContext context, conversation, LocalRecordingsProvider? previous) =>
              (previous?..setConversationProvider(conversation)) ?? LocalRecordingsProvider(),
        ),
        ChangeNotifierProxyProvider2<CaptureProvider, LocalRecordingsProvider, DeviceProvider>(
          create: (context) => DeviceProvider(),
          update: (BuildContext context, captureProvider, localRecordings, DeviceProvider? previous) =>
              (previous?..setProviders(captureProvider, localRecordings)) ?? DeviceProvider(),
        ),
        ChangeNotifierProxyProvider<DeviceProvider, OnboardingProvider>(
          create: (context) => OnboardingProvider(),
          update: (BuildContext context, device, OnboardingProvider? previous) =>
              (previous?..setDeviceProvider(device)) ?? OnboardingProvider(),
        ),
        ListenableProvider(create: (context) => HomeProvider()),
        ChangeNotifierProxyProvider<DeviceProvider, SpeechProfileProvider>(
          create: (context) => SpeechProfileProvider(),
          update: (BuildContext context, device, SpeechProfileProvider? previous) =>
              (previous?..setProviders(device)) ?? SpeechProfileProvider(),
        ),
        ChangeNotifierProxyProvider2<AppProvider, ConversationProvider, ConversationDetailProvider>(
          create: (context) => ConversationDetailProvider(),
          update: (BuildContext context, app, conversation, ConversationDetailProvider? previous) =>
              (previous?..setProviders(app, conversation)) ?? ConversationDetailProvider(),
        ),
        ChangeNotifierProxyProvider<AppProvider, AddAppProvider>(
          create: (context) => AddAppProvider(),
          update: (BuildContext context, value, AddAppProvider? previous) =>
              (previous?..setAppProvider(value)) ?? AddAppProvider(),
        ),
        ChangeNotifierProxyProvider<ConnectivityProvider, MemoriesProvider>(
          create: (context) => MemoriesProvider(),
          update: (context, connectivity, previous) =>
              (previous?..setConnectivityProvider(connectivity)) ?? MemoriesProvider(),
        ),
        ChangeNotifierProvider(create: (context) => UserProvider()),
        ChangeNotifierProvider(lazy: true, create: (context) => ActionItemsProvider()),
        ChangeNotifierProvider(lazy: true, create: (context) => GoalsProvider()..init()),
        ChangeNotifierProvider(lazy: true, create: (context) => TaskIntegrationProvider()),
        ChangeNotifierProvider(lazy: true, create: (context) => IntegrationProvider()),
        ChangeNotifierProvider(lazy: true, create: (context) => FolderProvider()),
        ChangeNotifierProvider(lazy: true, create: (context) => McpProvider()),
        ChangeNotifierProvider(create: (context) => VoiceRecorderProvider()..checkPendingRecording()),
        ChangeNotifierProvider(create: (context) => LocaleProvider()),
        ChangeNotifierProvider(create: (context) => AnnouncementProvider()),
        ChangeNotifierProvider(lazy: true, create: (context) => PhoneCallProvider()),
      ],
      builder: (context, child) {
        final app = WithForegroundTask(
          child: MaterialApp(
            debugShowCheckedModeBanner: F.env == Environment.dev,
            title: F.title,
            navigatorKey: MyApp.navigatorKey,
            locale: context.watch<LocaleProvider>().locale,
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: AppLocalizations.supportedLocales,
            theme: ThemeData(
              useMaterial3: false,
              colorScheme: const ColorScheme.dark(
                primary: Colors.black,
                secondary: Color(0xFF35343B),
                surface: Colors.black38,
              ),
              snackBarTheme: const SnackBarThemeData(
                backgroundColor: Color(0xFF1F1F25),
                contentTextStyle: TextStyle(fontSize: 16, color: Colors.white, fontWeight: FontWeight.w500),
              ),
              textTheme: TextTheme(
                titleLarge: const TextStyle(fontSize: 18, color: Colors.white),
                titleMedium: const TextStyle(fontSize: 16, color: Colors.white),
                bodyMedium: const TextStyle(fontSize: 14, color: Colors.white),
                labelMedium: TextStyle(fontSize: 12, color: Colors.grey.shade200),
              ),
              textSelectionTheme: const TextSelectionThemeData(
                cursorColor: Colors.white,
                selectionColor: Colors.white24,
                selectionHandleColor: Colors.white,
              ),
              cupertinoOverrideTheme: const CupertinoThemeData(
                primaryColor: Colors.white, // Controls the selection handles on iOS
              ),
            ),
            themeMode: ThemeMode.dark,
            builder: (context, child) {
              FlutterError.onError = (FlutterErrorDetails details) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  Logger.instance.talker.handle(details.exception, details.stack);
                  DebugLogManager.logError(details.exception, details.stack, 'FlutterError');
                });
              };
              ErrorWidget.builder = (errorDetails) {
                return CustomErrorWidget(errorMessage: errorDetails.exceptionAsString());
              };
              final content = child!;
              return PlatformService.isIOS && Env.posthogApiKey != null
                  ? RageClickContextTracker(child: content)
                  : content;
            },
            home: TalkerWrapper(
              talker: Logger.instance.talker,
              options: const TalkerWrapperOptions(enableErrorAlerts: false, enableExceptionAlerts: false),
              child: const AppShell(),
            ),
          ),
        );
        final auth = context.watch<AuthenticationProvider>();
        // The scope must sit above MaterialApp's Navigator. ConnectedDevice
        // opens on a new route, which cannot inherit providers inside home.
        return auth.isSignedIn() ? AuthenticatedProductScope(child: app) : app;
      },
    );
  }
}

class CustomErrorWidget extends StatelessWidget {
  final String errorMessage;

  const CustomErrorWidget({super.key, required this.errorMessage});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 50.0),
            const SizedBox(height: 10.0),
            Text(
              context.l10n.somethingWentWrong,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18.0, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10.0),
            Container(
              padding: const EdgeInsets.all(10),
              margin: const EdgeInsets.all(16),
              height: 200,
              decoration: BoxDecoration(
                color: const Color.fromARGB(255, 63, 63, 63),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(errorMessage, textAlign: TextAlign.start, style: const TextStyle(fontSize: 16.0)),
            ),
            const SizedBox(height: 10.0),
            SizedBox(
              width: 210,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: errorMessage));
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.errorCopied)));
                },
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Text(context.l10n.copyErrorMessage),
                    const SizedBox(width: 10),
                    const Icon(Icons.copy_rounded),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
