import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/mobile/authenticated_product_scope.dart';
import 'package:omi/providers/sync_provider.dart';

class _FakeSyncProvider extends ChangeNotifier implements SyncProvider {
  bool disposed = false;

  @override
  void dispose() {
    disposed = true;
    super.dispose();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  testWidgets('authenticated product pages can resolve their recording sync provider', (tester) async {
    final provider = _FakeSyncProvider();
    await tester.pumpWidget(
      AuthenticatedProductScope(
        createSyncProvider: () => provider,
        child: MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (routeContext) => Scaffold(
                      body: Text(
                        identical(routeContext.read<SyncProvider>(), provider) ? 'Sync ready' : 'Sync missing',
                      ),
                    ),
                  ),
                ),
                child: const Text('Open device route'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open device route'));
    await tester.pumpAndSettle();
    expect(find.text('Sync ready'), findsOneWidget);
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    expect(provider.disposed, isTrue);
  });
}
