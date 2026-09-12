import 'package:omi/widgets/local_scaffold.dart';
import 'package:flutter/material.dart';
import 'package:omi/pages/settings/selfhost_page.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

class LocalAccountsPage extends StatefulWidget {
  const LocalAccountsPage({super.key});
  @override
  State<LocalAccountsPage> createState() => _LocalAccountsPageState();
}

class _LocalAccountsPageState extends State<LocalAccountsPage> {
  List<dynamic> _users = [];
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final users = await localApi('v1/admin/users');
      if (mounted) {
        setState(() {
          _users = users;
          _error = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = context.l10n.somethingWentWrongTryAgain);
    }
  }

  Future<void> _edit([Map<String, dynamic>? user]) async {
    final email = TextEditingController(text: user?['email'] ?? '');
    final name = TextEditingController(text: user?['display_name'] ?? '');
    final password = TextEditingController();
    var enabled = user?['enabled'] != false;
    String? error;
    var busy = false;
    await showDialog<void>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
                  title: Text(context.l10n.account),
                  content: SizedBox(
                      width: 400,
                      child: SingleChildScrollView(
                          child: Column(mainAxisSize: MainAxisSize.min, children: [
                        TextField(
                            controller: email,
                            enabled: user == null,
                            keyboardType: TextInputType.emailAddress,
                            decoration: InputDecoration(labelText: context.l10n.email)),
                        if (user == null)
                          TextField(controller: name, decoration: InputDecoration(labelText: context.l10n.name)),
                        TextField(
                            controller: password,
                            obscureText: true,
                            decoration: InputDecoration(labelText: context.l10n.password)),
                        if (user != null)
                          SwitchListTile(
                              title: Text(context.l10n.enable),
                              value: enabled,
                              onChanged: user['uid'] == AuthService.instance.currentUser?.uid
                                  ? null
                                  : (value) => update(() => enabled = value)),
                        if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
                      ]))),
                  actions: [
                    TextButton(
                        style: localTextButtonStyle,
                        onPressed: busy ? null : () => Navigator.pop(context),
                        child: Text(context.l10n.cancel)),
                    FilledButton(
                        style: localFilledButtonStyle,
                        onPressed: busy
                            ? null
                            : () async {
                                update(() => busy = true);
                                try {
                                  await localApi('v1/admin/users${user == null ? '' : '/${user['uid']}'}',
                                      method: user == null ? 'POST' : 'PATCH',
                                      data: user == null
                                          ? {
                                              'email': email.text.trim(),
                                              'name': name.text.trim(),
                                              'password': password.text
                                            }
                                          : {
                                              'enabled': enabled,
                                              if (password.text.isNotEmpty) 'password': password.text
                                            });
                                  if (context.mounted) Navigator.pop(context);
                                } catch (_) {
                                  update(() {
                                    busy = false;
                                    error = context.l10n.somethingWentWrongTryAgain;
                                  });
                                }
                              },
                        child: Text(context.l10n.save))
                  ],
                )));
    for (final controller in [email, name, password]) {
      controller.dispose();
    }
    await _load();
  }

  @override
  Widget build(BuildContext context) => LocalScaffold(
        appBar: AppBar(title: Text(context.l10n.account)),
        floatingActionButton: FloatingActionButton(onPressed: _edit, child: const Icon(Icons.person_add)),
        body: RefreshIndicator(
            onRefresh: _load,
            child: ListView(children: [
              if (_error != null) Text(_error!),
              for (final user in _users)
                ListTile(
                    title: Text(user['email']),
                    subtitle: Text(user['display_name'] ?? ''),
                    leading: Icon(user['enabled'] == true ? Icons.person : Icons.person_off),
                    onTap: () => _edit(Map<String, dynamic>.from(user))),
            ])),
      );
}
