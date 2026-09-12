import 'package:omi/widgets/local_scaffold.dart';
import 'package:omi/utils/share_sheet.dart';
import 'dart:async';
import 'package:omi/pages/settings/local_integrations_page.dart';
import 'package:omi/pages/settings/local_accounts_page.dart';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as path;
import 'package:share_plus/share_plus.dart';
import 'package:uuid/uuid.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

Future<dynamic> localApi(String endpoint, {String method = 'GET', Object? data}) async {
  final response = await makeApiCall(
      url: '${AuthService.instance.serverUrl}$endpoint',
      headers: {},
      method: method,
      body: data == null ? '' : jsonEncode(data));
  if (response == null || response.statusCode < 200 || response.statusCode >= 300) {
    throw LocalAuthError(response?.statusCode ?? 0);
  }
  return response.body.isEmpty ? null : jsonDecode(response.body);
}

class SelfHostPage extends StatefulWidget {
  const SelfHostPage({super.key});
  @override
  State<SelfHostPage> createState() => _SelfHostPageState();
}

class _SelfHostPageState extends State<SelfHostPage> {
  List<dynamic> _profiles = [];
  List<dynamic> _voices = [];
  String? _voice;
  Map<String, dynamic> _selected = {};
  String? _error;
  bool _loading = true;
  @override
  void initState() {
    super.initState();
    _load();
    _loadVoices();
  }

  Future<void> _loadVoices() async {
    try {
      final voices = await localApi("v1/voices");
      if (mounted) setState(() => _voices = voices);
    } catch (_) {}
  }

  Future<void> _load() async {
    try {
      final profiles = await localApi(AuthService.instance.isAdmin ? 'v1/admin/ai-profiles' : 'v1/ai-profiles');
      final me = await localApi('v1/auth/me');
      if (mounted) {
        setState(() {
          _profiles = profiles;
          _selected = me['preferences']['ai_profiles'] ?? {};
          _voice = me['preferences']['voice'];
          _error = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = context.l10n.somethingWentWrongTryAgain);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _edit([Map<String, dynamic>? profile]) async {
    final name = TextEditingController(text: profile?['name'] ?? '');
    final url = TextEditingController(text: profile?['base_url'] ?? '');
    final model = TextEditingController(text: profile?['model'] ?? '');
    final key = TextEditingController();
    final options = TextEditingController(text: jsonEncode(profile?['capabilities']?['options'] ?? {}));
    var purpose = profile?['purpose'] ?? 'chat';
    var external = profile?['external'] == true;
    var enabled = profile?['enabled'] != false;
    var saving = false;
    String? error;
    await showDialog<void>(
        context: context,
        builder: (context) => StatefulBuilder(
            builder: (context, setDialog) => AlertDialog(
                  title: Text(context.l10n.model),
                  content: SizedBox(
                      width: 440,
                      child: SingleChildScrollView(
                          child: Column(mainAxisSize: MainAxisSize.min, children: [
                        TextField(controller: name, decoration: InputDecoration(labelText: context.l10n.name)),
                        DropdownButtonFormField<String>(
                            initialValue: purpose,
                            items: ['stt', 'chat', 'embedding']
                                .map((v) => DropdownMenuItem(value: v, child: Text(v)))
                                .toList(),
                            onChanged: profile != null ? null : (v) => purpose = v!),
                        TextField(
                            controller: url,
                            keyboardType: TextInputType.url,
                            decoration: InputDecoration(labelText: context.l10n.serverUrl)),
                        TextField(controller: model, decoration: InputDecoration(labelText: context.l10n.model)),
                        TextField(
                            controller: key,
                            obscureText: true,
                            decoration: InputDecoration(labelText: context.l10n.apiKey)),
                        TextField(
                            controller: options,
                            maxLines: 3,
                            decoration: InputDecoration(labelText: context.l10n.advancedSettings)),
                        SwitchListTile(
                            title: Text(context.l10n.externalAppAccess),
                            value: external,
                            onChanged: (v) => setDialog(() => external = v)),
                        SwitchListTile(
                            title: Text(context.l10n.enable),
                            value: enabled,
                            onChanged: (v) => setDialog(() => enabled = v)),
                        if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
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
                                setDialog(() => saving = true);
                                try {
                                  await localApi('v1/admin/ai-profiles${profile == null ? '' : '/${profile['id']}'}',
                                      method: profile == null ? 'POST' : 'PUT',
                                      data: {
                                        'name': name.text.trim(),
                                        'purpose': purpose,
                                        'base_url': url.text.trim(),
                                        'model': model.text.trim(),
                                        'enabled': enabled,
                                        'external': external,
                                        'options': jsonDecode(options.text),
                                        if (key.text.isNotEmpty) 'api_key': key.text,
                                      });
                                  if (context.mounted) Navigator.pop(context);
                                } catch (_) {
                                  setDialog(() {
                                    saving = false;
                                    error = context.l10n.somethingWentWrongTryAgain;
                                  });
                                }
                              },
                        child: Text(context.l10n.save))
                  ],
                )));
    for (final controller in [name, url, model, key, options]) {
      controller.dispose();
    }
    await _load();
  }

  @override
  Widget build(BuildContext context) => LocalScaffold(
        appBar: AppBar(title: Text(context.l10n.serverUrl)),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(padding: const EdgeInsets.all(20), children: [
                  SelectableText(AuthService.instance.serverUrl),
                  const SizedBox(height: 20),
                  if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
                  for (final purpose in ['stt', 'chat', 'embedding']) ...[
                    Text(purpose, style: Theme.of(context).textTheme.titleLarge),
                    for (final profile in _profiles.where((p) => p['purpose'] == purpose))
                      ListTile(
                        title: Text(profile['name']),
                        subtitle: Text(profile['model']),
                        leading: Radio<String>(
                            value: profile['id'],
                            groupValue: _selected[purpose],
                            onChanged: profile['enabled'] != true
                                ? null
                                : (value) async {
                                    try {
                                      await localApi('v1/users/me/ai-profiles', method: 'PUT', data: {purpose: value});
                                      await _load();
                                    } catch (_) {
                                      if (mounted) setState(() => _error = context.l10n.somethingWentWrongTryAgain);
                                    }
                                  }),
                        trailing: AuthService.instance.isAdmin
                            ? Row(mainAxisSize: MainAxisSize.min, children: [
                                IconButton(
                                    icon: const Icon(Icons.network_check),
                                    onPressed: () async {
                                      try {
                                        await localApi('v1/admin/ai-profiles/${profile['id']}/validate',
                                            method: 'POST');
                                        if (context.mounted) {
                                          ScaffoldMessenger.of(context)
                                              .showSnackBar(SnackBar(content: Text(context.l10n.saved)));
                                        }
                                      } catch (_) {
                                        if (mounted) setState(() => _error = context.l10n.connectionError);
                                      }
                                    }),
                                IconButton(
                                    icon: const Icon(Icons.edit),
                                    onPressed: () => _edit(Map<String, dynamic>.from(profile))),
                              ])
                            : null,
                      ),
                  ],
                  if (AuthService.instance.isAdmin)
                    FilledButton.icon(
                        style: localFilledButtonStyle,
                        onPressed: _edit,
                        icon: const Icon(Icons.add),
                        label: Text(context.l10n.add)),
                  if (AuthService.instance.isAdmin)
                    ListTile(
                        leading: const Icon(Icons.manage_accounts),
                        title: Text(context.l10n.account),
                        onTap: () =>
                            Navigator.push(context, MaterialPageRoute(builder: (_) => const LocalAccountsPage()))),
                  ListTile(
                      leading: const Icon(Icons.cable),
                      title: Text(context.l10n.integrations),
                      onTap: () =>
                          Navigator.push(context, MaterialPageRoute(builder: (_) => const LocalIntegrationsPage()))),
                  if (_voices.isNotEmpty)
                    DropdownButtonFormField<String>(
                        initialValue: _voices.any((v) => v['id'] == _voice) ? _voice : _voices.first['id'],
                        decoration: InputDecoration(labelText: context.l10n.voiceResponseAudio),
                        items: _voices
                            .map((v) => DropdownMenuItem<String>(value: v['id'], child: Text(v['name'])))
                            .toList(),
                        onChanged: (value) async {
                          try {
                            await localApi('v1/users/me', method: 'PATCH', data: {'voice': value});
                          } catch (_) {
                            if (mounted) setState(() => _error = context.l10n.connectionError);
                          }
                        }),
                  ListTile(
                      leading: const Icon(Icons.manage_search),
                      title: Text(context.l10n.refresh),
                      onTap: () async {
                        try {
                          await localApi('v1/users/me/reindex', method: 'POST');
                          if (context.mounted)
                            ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.saved)));
                        } catch (_) {
                          if (mounted) setState(() => _error = context.l10n.connectionError);
                        }
                      }),
                  const Divider(),
                  ListTile(
                      leading: const Icon(Icons.audio_file),
                      title: Text(context.l10n.importData),
                      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ImportAudioPage()))),
                  ListTile(
                      leading: const Icon(Icons.download),
                      title: Text(context.l10n.exportAllData),
                      onTap: () async {
                        try {
                          final data = await localApi('v1/export');
                          final file = File('${(await getTemporaryDirectory()).path}/ollomi-export.json');
                          await file.writeAsString(jsonEncode(data), flush: true);
                          await Share.shareXFiles([XFile(file.path)], sharePositionOrigin: shareSheetOrigin());
                        } catch (_) {
                          if (mounted) setState(() => _error = context.l10n.somethingWentWrongTryAgain);
                        }
                      }),
                ])),
      );
}

class ImportAudioPage extends StatefulWidget {
  final List<String> sharedPaths;
  const ImportAudioPage({super.key, this.sharedPaths = const []});
  @override
  State<ImportAudioPage> createState() => _ImportAudioPageState();
}

class _ImportAudioPageState extends State<ImportAudioPage> {
  List<File> _pending = [];
  List<dynamic> _jobs = [];
  Timer? _timer;
  String? _error;
  bool _busy = false;
  late final String _owner = '${AuthService.instance.instanceId}/${AuthService.instance.currentUser!.uid}';
  @override
  void initState() {
    super.initState();
    _loadShared();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  bool get _sameOwner => _owner == '${AuthService.instance.instanceId}/${AuthService.instance.currentUser?.uid}';
  Future<Directory> _directory() async =>
      Directory('${(await getApplicationSupportDirectory()).path}/imports/$_owner').create(recursive: true);
  Future<void> _loadShared() async {
    try {
      for (final file in widget.sharedPaths) {
        await _keep(File(file));
      }
      if (widget.sharedPaths.isNotEmpty) {
        await const MethodChannel('ollomi/audio_import').invokeMethod('acknowledge', {'paths': widget.sharedPaths});
      }
      await _load();
    } catch (_) {
      if (mounted) setState(() => _error = context.l10n.importErrorGeneric(''));
    }
  }

  Future<void> _keep(File source) async {
    if (!await source.exists()) return;
    final destination = File('${(await _directory()).path}/${const Uuid().v4()}${path.extension(source.path)}');
    await source.copy(destination.path);
  }

  Future<void> _load() async {
    if (!_sameOwner) return;
    final directory = await _directory();
    final pending = await directory.list().where((entry) => entry is File).cast<File>().toList();
    try {
      final jobs = await localApi('v1/import/jobs');
      if (mounted && _sameOwner) {
        setState(() {
          _pending = pending;
          _jobs = jobs['jobs'];
        });
      }
    } catch (_) {
      if (mounted && _sameOwner) {
        setState(() {
          _pending = pending;
        });
      }
    }
  }

  Future<void> _upload(File file) async {
    if (!_sameOwner) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final client = http.Client();
    try {
      final request = http.MultipartRequest('POST', Uri.parse('${AuthService.instance.serverUrl}v1/import/audio'))
        ..followRedirects = false
        ..headers.addAll(await buildHeaders(requireAuthCheck: true));
      request.files.add(await http.MultipartFile.fromPath('file', file.path));
      if (!_sameOwner || request.url.toString() != '${AuthService.instance.serverUrl}v1/import/audio') {
        throw const LocalAuthError(401);
      }
      final response = await http.Response.fromStream(await client.send(request).timeout(const Duration(minutes: 30)));
      if (response.statusCode != 202 || jsonDecode(response.body)['job_id'] == null) {
        throw LocalAuthError(response.statusCode);
      }
      await file.delete(); // Only after durable acceptance; a server error retains the local original.
      await _load();
    } catch (_) {
      if (mounted) setState(() => _error = context.l10n.importErrorGeneric(''));
    } finally {
      client.close();
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => LocalScaffold(
        appBar: AppBar(title: Text(context.l10n.importData)),
        floatingActionButton: FloatingActionButton(
            key: const Key('import-mp3'),
            onPressed: _busy
                ? null
                : () async {
                    try {
                      final result = await FilePicker.platform.pickFiles(
                          type: FileType.custom,
                          allowedExtensions: ['mp3', 'wav', 'm4a', 'ogg', 'flac'],
                          allowMultiple: true);
                      for (final file in result?.files ?? <PlatformFile>[]) {
                        if (file.path != null) await _keep(File(file.path!));
                      }
                      await _load();
                    } catch (_) {
                      if (mounted) setState(() => _error = context.l10n.importErrorOpeningFilePicker(''));
                    }
                  },
            child: const Icon(Icons.audio_file)),
        body: RefreshIndicator(
            onRefresh: _load,
            child: ListView(padding: const EdgeInsets.all(16), children: [
              if (_busy) const LinearProgressIndicator(),
              if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
              for (final file in _pending)
                ListTile(
                    title: Text(path.basename(file.path)),
                    leading: const Icon(Icons.audio_file),
                    subtitle: Text(context.l10n.saved),
                    trailing:
                        IconButton(icon: const Icon(Icons.upload), onPressed: _busy ? null : () => _upload(file))),
              for (final job in _jobs)
                ListTile(
                    title: Text(job['status']),
                    subtitle: Text('${job['progress']}%${job['error'] == null ? '' : '\n${job['error']}'}'),
                    onTap: job['status'] != 'completed'
                        ? null
                        : () async {
                            final data = await localApi('v1/conversations/${job['result']['conversation_id']}');
                            if (context.mounted) {
                              Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                      builder: (_) =>
                                          ConversationDetailPage(conversation: ServerConversation.fromJson(data))));
                            }
                          },
                    trailing: job['status'] == 'completed'
                        ? const Icon(Icons.chevron_right)
                        : IconButton(
                            icon: Icon(['failed', 'cancelled'].contains(job['status']) ? Icons.refresh : Icons.cancel),
                            onPressed: () async {
                              try {
                                await localApi(
                                    'v1/import/jobs/${job['id']}/${[
                                      'failed',
                                      'cancelled'
                                    ].contains(job['status']) ? 'retry' : 'cancel'}',
                                    method: 'POST');
                                await _load();
                              } catch (_) {
                                if (mounted) setState(() => _error = context.l10n.somethingWentWrongTryAgain);
                              }
                            })),
            ])),
      );
}
