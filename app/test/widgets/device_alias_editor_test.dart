import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/widgets/device_alias_editor.dart';

Widget _host(BtDevice device) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(
      body: Builder(
        builder: (context) => Center(
          child: ElevatedButton(
            onPressed: () => showModalBottomSheet<bool>(
              context: context,
              isScrollControlled: true,
              builder: (_) => DeviceAliasSheet(device: device),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
}

void main() {
  final device = BtDevice(id: 'dev-1', name: 'Omi CV 1', type: DeviceType.omi, rssi: -40);

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('saving a custom name persists it for that device', (tester) async {
    await tester.pumpWidget(_host(device));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('device_alias_field')), 'Omi de casa');
    await tester.tap(find.byKey(const Key('device_alias_save')));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().deviceAliasFor(device.id), 'Omi de casa');
  });

  testWidgets('reset clears the stored alias', (tester) async {
    await SharedPreferencesUtil().setDeviceAliasFor(device.id, 'Casa');

    await tester.pumpWidget(_host(device));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('device_alias_reset')));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().deviceAliasFor(device.id), '');
  });

  testWidgets('prefills the field with the existing alias', (tester) async {
    await SharedPreferencesUtil().setDeviceAliasFor(device.id, 'Casa');

    await tester.pumpWidget(_host(device));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    final field = tester.widget<TextField>(find.byKey(const Key('device_alias_field')));
    expect(field.controller?.text, 'Casa');
  });
}
