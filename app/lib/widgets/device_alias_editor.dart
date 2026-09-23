import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/l10n_extensions.dart';

class DeviceAliasSheet extends StatefulWidget {
  const DeviceAliasSheet({super.key, required this.device});

  final BtDevice device;

  @override
  State<DeviceAliasSheet> createState() => _DeviceAliasSheetState();
}

class _DeviceAliasSheetState extends State<DeviceAliasSheet> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: SharedPreferencesUtil().deviceAliasFor(widget.device.id));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await SharedPreferencesUtil().setDeviceAliasFor(widget.device.id, _controller.text);
    if (mounted) Navigator.of(context).pop(true);
  }

  Future<void> _reset() async {
    await SharedPreferencesUtil().setDeviceAliasFor(widget.device.id, '');
    if (mounted) Navigator.of(context).pop(false);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  margin: const EdgeInsets.only(bottom: 16),
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(color: const Color(0xFF3C3C43), borderRadius: BorderRadius.circular(2)),
                ),
              ),
              Text(
                context.l10n.deviceAliasTitle,
                style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              Text(
                context.l10n.deviceAliasDescription,
                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
              ),
              const SizedBox(height: 16),
              TextField(
                key: const Key('device_alias_field'),
                controller: _controller,
                autofocus: true,
                maxLength: 40,
                style: const TextStyle(color: Colors.white),
                cursorColor: Colors.white,
                decoration: InputDecoration(
                  hintText: context.l10n.deviceAliasHint,
                  hintStyle: const TextStyle(color: Color(0xFF8E8E93)),
                  counterStyle: const TextStyle(color: Color(0xFF8E8E93)),
                  filled: true,
                  fillColor: const Color(0xFF2A2A2E),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: _AliasActionButton(
                      buttonKey: const Key('device_alias_reset'),
                      label: context.l10n.reset,
                      filled: false,
                      onTap: _reset,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _AliasActionButton(
                      buttonKey: const Key('device_alias_save'),
                      label: context.l10n.save,
                      filled: true,
                      onTap: _save,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AliasActionButton extends StatelessWidget {
  const _AliasActionButton({
    required this.buttonKey,
    required this.label,
    required this.filled,
    required this.onTap,
  });

  final Key buttonKey;
  final String label;
  final bool filled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      key: buttonKey,
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: filled ? Colors.white : const Color(0xFF2A2A2E),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Center(
          child: Text(
            label,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: filled ? Colors.black : Colors.white,
            ),
          ),
        ),
      ),
    );
  }
}
