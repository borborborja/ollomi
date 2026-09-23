import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/providers/device_provider.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider({required this.connected});

  final bool connected;

  @override
  bool get isConnected => connected;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _app(DeviceProvider provider) {
  return ChangeNotifierProvider<DeviceProvider>.value(
    value: provider,
    child: MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: const Scaffold(body: SettingsDrawer()),
    ),
  );
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('hides the device settings entry when no device is connected', (tester) async {
    final provider = _StubDeviceProvider(connected: false);
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.text('Device Settings'), findsNothing);
  });

  testWidgets('shows the device settings entry when a device is connected', (tester) async {
    final provider = _StubDeviceProvider(connected: true);
    addTearDown(provider.dispose);

    await tester.pumpWidget(_app(provider));
    await tester.pump();

    expect(find.text('Device Settings'), findsOneWidget);
  });
}
