import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/sync_provider.dart';

/// Owns recording sync for the signed-in product subtree. The provider must
/// not outlive an account: WAL state and upload recovery belong to that user.
class AuthenticatedProductScope extends StatelessWidget {
  final Widget child;
  final SyncProvider Function()? createSyncProvider;

  const AuthenticatedProductScope({super.key, required this.child, this.createSyncProvider});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<SyncProvider>(
      create: (_) => (createSyncProvider ?? SyncProvider.new)(),
      child: child,
    );
  }
}
