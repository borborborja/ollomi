import 'package:flutter/material.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Upstream support hooks now open local help; identity/analytics hooks collect nothing.
class IntercomManager {
  static final instance = IntercomManager();
  IntercomManager get intercom => this;
  Future<void> displayMessenger() async {
    final context = globalNavigatorKey.currentContext;
    if (context == null) return;
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Ollomi'), content: Text(context.l10n.serverUrl),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: Text(context.l10n.close))],
    ));
  }
  Future<void> initIntercom() async { }
  Future<void> loginIdentifiedUser(String uid) async { }
  Future<void> loginUnidentifiedUser() async { }
  Future<void> displayChargingArticle(String device) => displayMessenger();
  Future<void> displayEarnMoneyArticle() => displayMessenger();
  Future<void> displayFirmwareUpdateArticle() => displayMessenger();
  Future<void> logEvent(String eventName, {Map<String, dynamic>? metaData}) async { }
  Future<void> updateCustomAttributes(Map<String, dynamic> attributes) async { }
  Future<void> updateUser(String? email, String? name, String? uid) async { }
  Future<void> setUserAttributes() async { }
  Future<void> sendTokenToIntercom(String token) async { }
}
