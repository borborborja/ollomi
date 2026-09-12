import 'package:flutter/material.dart';
import 'package:omi/pages/settings/local_integrations_page.dart';

class AppsPage extends StatefulWidget {
  final bool showAppBar;
  const AppsPage({super.key, this.showAppBar = false});
  @override
  State<AppsPage> createState() => AppsPageState();
}

class AppsPageState extends State<AppsPage> {
  void scrollToTop() {}
  @override
  Widget build(BuildContext context) => const LocalIntegrationsPage();
}
