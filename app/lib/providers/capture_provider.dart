import 'dart:async';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/utils/logger.dart';

class CaptureProvider extends CaptureController {
  CaptureProvider({
    super.externalActions,
    super.conversationLocationCapture,
    super.inProgressConversationLoader,
    super.audioCodecLoader,
    super.microphonePermissionRequester,
    super.phoneMicBatchRecorder,
    super.recordingTelemetry,
    LocalSegmentStore? localSegmentStore,
  }) : localSegmentStore = localSegmentStore ?? LocalSegmentStore.disabled() {
    addListener(_persistLiveSegments);
  }

  final LocalSegmentStore localSegmentStore;
  String? _lastPersistedFingerprint;
  Future<void> _liveSegmentWrite = Future<void>.value();

  Future<void> get pendingLiveSegmentWrite => _liveSegmentWrite;

  @override
  Future<List<TranscriptSegment>> loadLocalSegments(String sessionId) {
    if (!localSegmentStore.enabled) return Future.value(const []);
    return localSegmentStore.loadSession(sessionId);
  }

  @override
  Future<List<TranscriptSegment>> loadLatestLocalSegments() {
    if (!localSegmentStore.enabled) return Future.value(const []);
    return localSegmentStore.loadLatestSession();
  }

  @override
  Future<void> releaseLocalSegments(String sessionId) {
    if (!localSegmentStore.enabled) return Future.value();
    _lastPersistedFingerprint = null;
    return localSegmentStore.release(sessionId);
  }

  void _persistLiveSegments() {
    if (!localSegmentStore.enabled) return;
    final sessionId = activeCaptureSessionId ?? activeRecordingId;
    if (sessionId == null) return;
    // Never erase a durable copy with an empty list: session teardown clears
    // the in-memory list before the conversation is finalized.
    if (segments.isEmpty && !isCaptureActive) return;
    final fingerprint = segments
        .map((segment) =>
            '${segment.id}:${segment.speaker}:${segment.speakerId}:${segment.isUser}:${segment.personId ?? ''}:${segment.text}')
        .join('\n');
    if (fingerprint == _lastPersistedFingerprint) return;
    _lastPersistedFingerprint = fingerprint;
    final pending = List.of(segments);
    _liveSegmentWrite =
        _liveSegmentWrite.then((_) => localSegmentStore.replaceSession(sessionId, pending)).catchError((Object e) {
      Logger.debug('Error persisting live segments: $e');
      if (_lastPersistedFingerprint == fingerprint) {
        _lastPersistedFingerprint = null;
      }
    });
    unawaited(_liveSegmentWrite);
  }

  @override
  void dispose() {
    removeListener(_persistLiveSegments);
    super.dispose();
  }
}
