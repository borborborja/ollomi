import 'package:flutter/material.dart';

/// Material controls on local administration pages need visible focus/selection
/// colors; the upstream custom UI uses black as its primary brand color.
class LocalScaffold extends StatelessWidget {
  const LocalScaffold({super.key, this.appBar, this.body, this.floatingActionButton});
  final PreferredSizeWidget? appBar;
  final Widget? body;
  final Widget? floatingActionButton;

  @override
  Widget build(BuildContext context) => Theme(
        data: Theme.of(context).copyWith(
          colorScheme: Theme.of(context).colorScheme.copyWith(
                primary: const Color(0xFFBA99FF),
                onPrimary: Colors.black,
                secondary: const Color(0xFFBA99FF),
                onSecondary: Colors.black,
              ),
        ),
        child: Scaffold(appBar: appBar, body: body, floatingActionButton: floatingActionButton),
      );
}

const localFilledButtonStyle = ButtonStyle(
  backgroundColor: WidgetStatePropertyAll(Color(0xFFBA99FF)),
  foregroundColor: WidgetStatePropertyAll(Colors.black),
);
const localTextButtonStyle = ButtonStyle(
  foregroundColor: WidgetStatePropertyAll(Color(0xFFBA99FF)),
);
