import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/selfhost_page.dart';

void main() {
  testWidgets('environment profiles show active model and health without editors', (tester) async {
    const purposeStatus = {
      'active_profile_id': 'primary',
      'profiles': [
        {
          'id': 'primary',
          'name': 'Local chat',
          'provider': 'ollama',
          'model': 'qwen3:4b',
          'status': 'healthy',
        },
        {
          'id': 'fallback',
          'name': 'Cloud fallback',
          'provider': 'openrouter',
          'model': 'openai/gpt-test',
          'status': 'unhealthy',
        },
      ],
    };

    var selected = 0;

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: EnvironmentAiProfileList(
            purposeStatus: purposeStatus,
            selectedId: 'primary',
            selectionAllowed: false,
            onSelected: (_) => selected++,
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.textContaining('qwen3:4b'), findsOneWidget);
    expect(find.textContaining('openai/gpt-test'), findsOneWidget);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    expect(find.byIcon(Icons.error), findsOneWidget);
    expect(find.byIcon(Icons.edit), findsNothing);
    // selectionAllowed is false: the server owns the profile, so both radios are
    // inert and a tap must not reach the selection callback.
    expect(find.byType(Radio<String>), findsNWidgets(2));
    await tester.tap(find.byType(Radio<String>).last);
    await tester.pumpAndSettle();
    expect(selected, 0);
  });
}
