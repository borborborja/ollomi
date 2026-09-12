import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AuthComponent extends StatefulWidget {
  final VoidCallback onSignIn;
  const AuthComponent({super.key, required this.onSignIn});
  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  final _server = TextEditingController(text: AuthService.instance.serverUrl);
  final _email = TextEditingController();
  final _password = TextEditingController();
  String? _error;
  @override
  void dispose() {
    _server.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthenticationProvider>();
    return SafeArea(
        child: Center(
            child: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Card(
              child: Padding(
            padding: const EdgeInsets.all(24),
            child: AutofillGroup(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text('Ollomi', style: Theme.of(context).textTheme.headlineLarge),
              const SizedBox(height: 24),
              TextField(
                  key: const Key('server-url'),
                  controller: _server,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  decoration:
                      InputDecoration(labelText: context.l10n.serverUrl, hintText: 'https://ollomi.example.org')),
              TextField(
                  key: const Key('login-email'),
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.username],
                  decoration: InputDecoration(labelText: context.l10n.email)),
              TextField(
                  key: const Key('login-password'),
                  controller: _password,
                  obscureText: true,
                  autofillHints: const [AutofillHints.password],
                  decoration: InputDecoration(labelText: context.l10n.password)),
              if (_error != null)
                Padding(
                    padding: const EdgeInsets.all(12), child: Text(_error!, style: const TextStyle(color: Colors.red))),
              const SizedBox(height: 24),
              FilledButton(
                  style:
                      FilledButton.styleFrom(backgroundColor: const Color(0xFFBA99FF), foregroundColor: Colors.black),
                  key: const Key('local-login'),
                  onPressed: auth.loading
                      ? null
                      : () async {
                          setState(() => _error = null);
                          try {
                            await auth.signIn(_server.text, _email.text, _password.text, widget.onSignIn);
                          } catch (_) {
                            if (mounted) setState(() => _error = context.l10n.authenticationFailed);
                          }
                        },
                  child: auth.loading ? const CircularProgressIndicator() : Text(context.l10n.continueButton)),
            ])),
          ))),
    )));
  }
}
