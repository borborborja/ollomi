import 'package:omi/widgets/local_scaffold.dart';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:omi/pages/settings/selfhost_page.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

class LocalIntegrationsPage extends StatefulWidget {
  const LocalIntegrationsPage({super.key});
  @override
  State<LocalIntegrationsPage> createState() => _LocalIntegrationsPageState();
}

class _LocalIntegrationsPageState extends State<LocalIntegrationsPage> {
  List<dynamic> _items = [];
  String? _error;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final items = await localApi('v1/local/integrations');
      if (mounted) {
        setState(() {
          _items = items;
          _error = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = context.l10n.connectionError);
    }
  }

  Future<void> _edit([Map<String, dynamic>? item]) async {
    final name = TextEditingController(text: item?['name'] ?? '');
    final url = TextEditingController(text: item?['base_url'] ?? '');
    final username = TextEditingController(text: item?['username'] ?? '');
    final secret = TextEditingController();
    var kind = item?['kind'] ?? 'webdav';
    var enabled = item?['enabled'] != false;
    String? error;
    var saving = false;
    await showDialog<void>(
        context: context,
        builder: (context) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
                  title: Text(context.l10n.integrations),
                  content: SizedBox(
                      width: 400,
                      child: SingleChildScrollView(
                          child: Column(mainAxisSize: MainAxisSize.min, children: [
                        TextField(controller: name, decoration: InputDecoration(labelText: context.l10n.name)),
                        DropdownButtonFormField<String>(
                            initialValue: kind,
                            items: ['webdav', 'caldav', 'webhook', 'mcp']
                                .map((v) => DropdownMenuItem(value: v, child: Text(v)))
                                .toList(),
                            onChanged: (v) => kind = v!),
                        TextField(controller: url, decoration: InputDecoration(labelText: context.l10n.serverUrl)),
                        TextField(controller: username, decoration: InputDecoration(labelText: context.l10n.user)),
                        TextField(
                            controller: secret,
                            obscureText: true,
                            decoration: InputDecoration(labelText: context.l10n.password)),
                        SwitchListTile(
                            title: Text(context.l10n.enable),
                            value: enabled,
                            onChanged: (v) => update(() => enabled = v)),
                        if (error != null) Text(error!),
                      ]))),
                  actions: [
                    TextButton(
                        style: localTextButtonStyle,
                        onPressed: saving ? null : () => Navigator.pop(context),
                        child: Text(context.l10n.cancel)),
                    FilledButton(
                        style: localFilledButtonStyle,
                        onPressed: saving
                            ? null
                            : () async {
                                update(() => saving = true);
                                try {
                                  await localApi('v1/admin/integrations${item == null ? '' : '/${item['id']}'}',
                                      method: item == null ? 'POST' : 'PUT',
                                      data: {
                                        'name': name.text,
                                        'base_url': url.text,
                                        'username': username.text,
                                        'kind': kind,
                                        'enabled': enabled,
                                        if (secret.text.isNotEmpty) 'secret': secret.text
                                      });
                                  if (context.mounted) Navigator.pop(context);
                                } catch (_) {
                                  update(() {
                                    saving = false;
                                    error = context.l10n.connectionError;
                                  });
                                }
                              },
                        child: Text(context.l10n.save))
                  ],
                )));
    for (final c in [name, url, username, secret]) {
      c.dispose();
    }
    await _load();
  }

  Future<void> _run(Map<String, dynamic> item) async {
    if (item['kind'] == 'mcp') {
      try {
        final result = await localApi('v1/local/integrations/${item['id']}/tools');
        if (!mounted) return;
        await showModalBottomSheet<void>(
            context: context,
            isScrollControlled: true,
            builder: (context) => SafeArea(
                    child: ListView(shrinkWrap: true, children: [
                  for (final tool in result['tools'] ?? [])
                    ListTile(
                        title: Text(tool['name']),
                        subtitle: Text(tool['description'] ?? ''),
                        onTap: () async {
                          Navigator.pop(context);
                          await _tool(item, Map<String, dynamic>.from(tool));
                        }),
                ])));
      } catch (_) {
        if (mounted) setState(() => _error = context.l10n.mcpConnectionFailed);
      }
      return;
    }
    final confirm = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
                title: Text(context.l10n.exportAllData),
                content: Text('${item['name']}\n${item['base_url']}'),
                actions: [
                  TextButton(
                      style: localTextButtonStyle,
                      onPressed: () => Navigator.pop(context, false),
                      child: Text(context.l10n.cancel)),
                  FilledButton(
                      style: localFilledButtonStyle,
                      onPressed: () => Navigator.pop(context, true),
                      child: Text(context.l10n.exportAllData)),
                ]));
    if (confirm != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await localApi('v1/local/integrations/${item['id']}/export', method: 'POST');
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.saved)));
    } catch (_) {
      if (mounted) setState(() => _error = context.l10n.connectionError);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _tool(Map<String, dynamic> item, Map<String, dynamic> tool) async {
    final arguments = TextEditingController(text: '{}');
    String? result;
    var busy = false;
    await showDialog<void>(
        context: context,
        builder: (context) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
                  title: Text(tool['name']),
                  content: SizedBox(
                      width: 440,
                      child: SingleChildScrollView(
                          child: Column(mainAxisSize: MainAxisSize.min, children: [
                        SelectableText(jsonEncode(tool['inputSchema'])),
                        TextField(
                            controller: arguments,
                            maxLines: 5,
                            decoration: InputDecoration(labelText: context.l10n.advancedSettings)),
                        if (result != null) SelectableText(result!),
                      ]))),
                  actions: [
                    TextButton(
                        style: localTextButtonStyle,
                        onPressed: busy ? null : () => Navigator.pop(context),
                        child: Text(context.l10n.close)),
                    FilledButton(
                        style: localFilledButtonStyle,
                        onPressed: busy
                            ? null
                            : () async {
                                update(() => busy = true);
                                try {
                                  final response = await localApi('v1/local/integrations/${item['id']}/call',
                                      method: 'POST',
                                      data: {'name': tool['name'], 'arguments': jsonDecode(arguments.text)});
                                  update(() => result = const JsonEncoder.withIndent('  ').convert(response));
                                } catch (_) {
                                  update(() => result = context.l10n.mcpConnectionFailed);
                                } finally {
                                  update(() => busy = false);
                                }
                              },
                        child: Text(context.l10n.send)),
                  ],
                )));
    arguments.dispose();
  }

  @override
  Widget build(BuildContext context) => LocalScaffold(
        appBar: AppBar(title: Text(context.l10n.integrations)),
        floatingActionButton:
            AuthService.instance.isAdmin ? FloatingActionButton(onPressed: _edit, child: const Icon(Icons.add)) : null,
        body: RefreshIndicator(
            onRefresh: _load,
            child: ListView(children: [
              if (_busy) const LinearProgressIndicator(),
              if (_error != null) Text(_error!),
              for (final item in _items)
                ListTile(
                    title: Text(item['name']),
                    subtitle: Text('${item['kind']} · ${item['base_url']}'),
                    leading: IconButton(
                        icon: const Icon(Icons.play_arrow),
                        onPressed:
                            _busy || item['enabled'] != true ? null : () => _run(Map<String, dynamic>.from(item))),
                    trailing: AuthService.instance.isAdmin
                        ? IconButton(
                            icon: const Icon(Icons.edit), onPressed: () => _edit(Map<String, dynamic>.from(item)))
                        : null),
            ])),
      );
}
