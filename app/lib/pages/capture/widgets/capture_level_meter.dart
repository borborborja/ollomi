import 'package:flutter/material.dart';

/// Discreet live audio level for the recording surfaces: three rounded bars
/// that follow the smoothed capture level.
///
/// Purely decorative, so it stays out of the semantics tree (the status text
/// already announces the capture state).
class CaptureLevelMeter extends StatefulWidget {
  const CaptureLevelMeter({super.key, required this.level, this.compact = false});

  /// Smoothed level in the 0..1 range.
  final double level;

  /// Compact variant used inside list cards and the home capture bar.
  final bool compact;

  @override
  State<CaptureLevelMeter> createState() => _CaptureLevelMeterState();
}

class _CaptureLevelMeterState extends State<CaptureLevelMeter> with SingleTickerProviderStateMixin {
  // Uneven weights give the three bars an equalizer silhouette instead of a
  // single block moving up and down.
  static const List<double> _weights = [0.62, 1.0, 0.78];

  late final AnimationController _controller;
  late double _from;
  late double _to;

  @override
  void initState() {
    super.initState();
    _from = widget.level.clamp(0.0, 1.0);
    _to = _from;
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 120),
      value: 1.0,
    );
  }

  @override
  void didUpdateWidget(covariant CaptureLevelMeter oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.level != oldWidget.level) {
      _from = _displayedLevel;
      _to = widget.level.clamp(0.0, 1.0);
      _controller.forward(from: 0);
    }
  }

  double get _displayedLevel => _from + (_to - _from) * _controller.value;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final height = widget.compact ? 13.0 : 20.0;
    final barWidth = widget.compact ? 3.0 : 4.0;
    final gap = widget.compact ? 2.5 : 3.0;
    return ExcludeSemantics(
      child: RepaintBoundary(
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, child) {
            final level = _displayedLevel;
            return SizedBox(
              height: height,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  for (var index = 0; index < _weights.length; index++) ...[
                    if (index > 0) SizedBox(width: gap),
                    _bar(height: height, width: barWidth, level: level * _weights[index]),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _bar({required double height, required double width, required double level}) {
    final value = level.clamp(0.0, 1.0);
    return Container(
      width: width,
      height: height * (0.2 + 0.8 * value),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.4 + 0.6 * value),
        borderRadius: BorderRadius.circular(width / 2),
      ),
    );
  }
}
