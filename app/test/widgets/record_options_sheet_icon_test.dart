import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';

void main() {
  // Regression test: FaIcon (unlike material Icon) has no internal Center, so
  // without an alignment on the fixed-size circle container the glyph painted
  // at the top-left, outside the circle.
  testWidgets('record option icons are centered inside their circles', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: RecordOptionsSheet(
            onPickPhoneMic: () {},
            onPickPhoneCall: () {},
            connectedDeviceName: 'Omi',
            onPickConnectedDevice: () {},
            onImportAudio: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final icons = find.byType(FaIcon);
    expect(icons, findsNWidgets(4));

    for (final icon in icons.evaluate()) {
      final iconRect = tester.getRect(find.byWidget(icon.widget));
      final circle = find.ancestor(of: find.byWidget(icon.widget), matching: find.byType(Container)).first;
      final circleRect = tester.getRect(circle);

      expect(circleRect.size, const Size(44, 44));
      // Without the fix the circle passes tight 44x44 constraints to the
      // FaIcon, whose glyph then paints at the top-left, outside the circle.
      // With alignment set, constraints are loosened: the icon's render box
      // keeps its natural ~18px size and is centered inside the circle.
      expect(iconRect.width, lessThan(circleRect.width), reason: 'icon box inflated by tight constraints');
      expect(iconRect.height, lessThan(circleRect.height), reason: 'icon box inflated by tight constraints');
      expect(iconRect.center.dx, closeTo(circleRect.center.dx, 0.5));
      expect(iconRect.center.dy, closeTo(circleRect.center.dy, 0.5));
    }
  });

  testWidgets('record options expose connected-device and audio-import sources', (tester) async {
    var deviceSelected = false;
    var importSelected = false;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: RecordOptionsSheet(
            onPickPhoneMic: () {},
            onPickPhoneCall: () {},
            connectedDeviceName: 'Friend Pendant',
            onPickConnectedDevice: () => deviceSelected = true,
            onImportAudio: () => importSelected = true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Record: Friend Pendant'), findsOneWidget);
    expect(find.text('Import Data: Recordings'), findsOneWidget);
    expect(find.text('MP3 · M4A · WAV · OGG · FLAC'), findsOneWidget);

    await tester.tap(find.byKey(const Key('record-source-connected-device')));
    await tester.tap(find.byKey(const Key('record-source-import-audio')));
    expect(deviceSelected, isTrue);
    expect(importSelected, isTrue);
  });

  testWidgets('record options omit the device source when nothing is connected', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: RecordOptionsSheet(
            onPickPhoneMic: () {},
            onPickPhoneCall: () {},
            onImportAudio: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('record-source-connected-device')), findsNothing);
    expect(find.byKey(const Key('record-source-import-audio')), findsOneWidget);
  });
}
