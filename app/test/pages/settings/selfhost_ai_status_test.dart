import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/selfhost_page.dart';

void main() {
  testWidgets('environment profiles show active model and health without editors', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: EnvironmentAiProfileList(
            purposeStatus: {
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
            },
          ),
        ),
      ),
    );

    expect(find.textContaining('qwen3:4b'), findsOneWidget);
    expect(find.textContaining('openai/gpt-test'), findsOneWidget);
    expect(find.text('Active'), findsOneWidget);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    expect(find.byIcon(Icons.error), findsOneWidget);
    expect(find.byType(Radio<String>), findsNothing);
    expect(find.byIcon(Icons.edit), findsNothing);
  });
}
