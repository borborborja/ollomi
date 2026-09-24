import 'package:flutter/material.dart';

import 'package:omi/pages/capture/widgets/capture_level_meter.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/utils/l10n_extensions.dart';

String captureSourceLabel(BuildContext context, CaptureUiState state) {
  return switch (state.source) {
    CaptureUiSource.device => state.deviceName ?? context.l10n.device,
    CaptureUiSource.systemAudio => context.l10n.screenRecording,
    CaptureUiSource.phone => context.l10n.memoryThisDevice,
  };
}

String captureStageLabel(BuildContext context, CaptureUiState state) {
  return switch (state.stage) {
    CaptureUiStage.inactive => '',
    CaptureUiStage.preparing => context.l10n.preparingAudioCapture,
    CaptureUiStage.waitingForAudio => context.l10n.listeningForAudio,
    CaptureUiStage.receivingAudio => context.l10n.audioDataReceived,
    CaptureUiStage.transcribing => context.l10n.transcribing,
    CaptureUiStage.noSpeech => context.l10n.captureNoSpeechDetected,
    CaptureUiStage.transcriptionUnavailable => context.l10n.captureTranscriptionUnavailableRecordingContinues,
    CaptureUiStage.transcriptionDelayed => context.l10n.captureTranscriptionDelayed,
    CaptureUiStage.reconnecting => context.l10n.transcriptionPausedReconnecting,
    CaptureUiStage.paused => context.l10n.paused,
    CaptureUiStage.offline => context.l10n.transcribeLaterTitle,
  };
}

class CaptureStatusView extends StatelessWidget {
  const CaptureStatusView({
    super.key,
    required this.state,
    this.compact = false,
  });

  final CaptureUiState state;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final status = captureStageLabel(context, state);
    final source = captureSourceLabel(context, state);
    final level = state.audioLevel?.clamp(0.0, 1.0) ?? 0.0;
    final isProblem = state.stage == CaptureUiStage.transcriptionUnavailable ||
        state.stage == CaptureUiStage.transcriptionDelayed ||
        state.stage == CaptureUiStage.reconnecting;
    final dotColor = state.stage == CaptureUiStage.paused
        ? Colors.orange
        : isProblem
            ? Colors.amber
            : const Color(0xFFFE5D50);

    if (compact) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 7, height: 7, decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle)),
          const SizedBox(width: 7),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 240),
            child: Text(
              '$status · $source',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Color(0xFFC9CBCF), fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      );
    }

    return Semantics(
      label: '$status. $source',
      liveRegion: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            isProblem ? Icons.cloud_off_rounded : Icons.graphic_eq_rounded,
            color: dotColor,
            size: 34,
          ),
          const SizedBox(height: 14),
          Text(
            status,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          Text(
            source,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Color(0xFFB5B5BA), fontSize: 14),
          ),
          const SizedBox(height: 16),
          CaptureLevelMeter(
            key: const Key('capture-server-audio-level'),
            level: level,
          ),
        ],
      ),
    );
  }
}
