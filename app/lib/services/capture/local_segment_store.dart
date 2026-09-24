import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/transcript_hash.dart';
import 'package:path_provider/path_provider.dart';

/// Durable live-caption segments for S21 / S22.
///
/// File-backed JSON under application-support `local_segments/`, not
/// sqflite/Drift — `app/` has no SQLite plugin today and this shard must
/// not add a native dependency. The bytes on disk are the v5 hash payload
/// (speaker, speaker_id, is_user, person_id, text) plus timings/ids S22
/// will need. [release] deletes a session after the projection is accepted.
class LocalSegmentStore {
  LocalSegmentStore._({required this.enabled, Directory? directory}) : _directory = directory;

  factory LocalSegmentStore.disabled() => LocalSegmentStore._(enabled: false);

  factory LocalSegmentStore.at(Directory directory) => LocalSegmentStore._(enabled: true, directory: directory);

  /// Lazy application-support directory. Safe to construct off the first write.
  factory LocalSegmentStore.appSupport() => LocalSegmentStore._(enabled: true);

  static const folderName = 'local_segments';

  final bool enabled;
  Directory? _directory;

  static int _lastSavedAtMillis = 0;

  static int _nextSavedAtMillis() {
    final now = DateTime.now().millisecondsSinceEpoch;
    _lastSavedAtMillis = now > _lastSavedAtMillis ? now : _lastSavedAtMillis + 1;
    return _lastSavedAtMillis;
  }

  Future<Directory> resolveDirectory() async {
    if (_directory != null) return _directory!;
    final root = await getApplicationSupportDirectory();
    final dir = Directory('${root.path}/$folderName');
    await dir.create(recursive: true);
    _directory = dir;
    return dir;
  }

  File _fileFor(Directory dir, String sessionId) {
    final safe = sessionId.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
    return File('${dir.path}/$safe.json');
  }

  Future<void> replaceSession(String sessionId, List<TranscriptSegment> segments) async {
    if (!enabled) return;
    final dir = await resolveDirectory();
    await dir.create(recursive: true);
    final file = _fileFor(dir, sessionId);
    final tmp = File('${file.path}.tmp');
    final payload = <String, Object?>{
      'encoding_version': transcriptHashEncodingVersion,
      'session_id': sessionId,
      // Monotonic write stamp so "latest session" never depends on filesystem
      // mtime granularity.
      'saved_at_millis': _nextSavedAtMillis(),
      'transcript_sha256': transcriptSha256(segments),
      'segments': segments.map(_segmentToJson).toList(),
    };
    await tmp.writeAsString(jsonEncode(payload));
    if (await file.exists()) {
      await file.delete();
    }
    await tmp.rename(file.path);
  }

  Future<List<TranscriptSegment>> loadSession(String sessionId) async {
    if (!enabled) return const [];
    final dir = await resolveDirectory();
    final file = _fileFor(dir, sessionId);
    if (!await file.exists()) return const [];
    return _decodeSegments(await file.readAsString());
  }

  /// Segments of the most recently written session.
  ///
  /// A restarted app has no in-memory session id, but a foreground capture can
  /// still be running; this lets the live screen restore what was already
  /// transcribed instead of showing an empty transcript.
  Future<List<TranscriptSegment>> loadLatestSession() async {
    if (!enabled) return const [];
    final dir = await resolveDirectory();
    if (!await dir.exists()) return const [];
    final files = (await dir.list().toList()).whereType<File>().where((file) => file.path.endsWith('.json'));
    List<TranscriptSegment> latest = const [];
    var latestStamp = -1;
    for (final file in files) {
      try {
        final decoded = jsonDecode(await file.readAsString());
        if (decoded is! Map<String, dynamic>) continue;
        final stamp = decoded['saved_at_millis'];
        final savedAt = stamp is int ? stamp : 0;
        if (savedAt < latestStamp) continue;
        latestStamp = savedAt;
        latest = _segmentsFromPayload(decoded);
      } catch (_) {
        continue;
      }
    }
    return latest;
  }

  static List<TranscriptSegment> _decodeSegments(String content) {
    final decoded = jsonDecode(content);
    if (decoded is! Map<String, dynamic>) return const [];
    return _segmentsFromPayload(decoded);
  }

  static List<TranscriptSegment> _segmentsFromPayload(Map<String, dynamic> decoded) {
    final raw = decoded['segments'];
    if (raw is! List) return const [];
    return raw.whereType<Map<String, dynamic>>().map(_segmentFromJson).toList();
  }

  Future<String?> loadDigest(String sessionId) async {
    if (!enabled) return null;
    final dir = await resolveDirectory();
    final file = _fileFor(dir, sessionId);
    if (!await file.exists()) return null;
    final decoded = jsonDecode(await file.readAsString());
    if (decoded is! Map<String, dynamic>) return null;
    final digest = decoded['transcript_sha256'];
    return digest is String ? digest : null;
  }

  Future<void> release(String sessionId) async {
    if (!enabled) return;
    final dir = await resolveDirectory();
    final file = _fileFor(dir, sessionId);
    if (await file.exists()) {
      await file.delete();
    }
  }

  static const draftFolderName = 'drafts';

  /// Persist the live transcript of a conversation the server is still
  /// processing, keyed by conversation id, so the draft survives an app restart.
  Future<void> replaceDraft(
    String conversationId,
    int sessionStartSeconds,
    List<TranscriptSegment> segments,
  ) async {
    if (!enabled) return;
    final drafts = await _resolveDraftDirectory();
    final file = _fileFor(drafts, conversationId);
    final tmp = File('${file.path}.tmp');
    final payload = <String, Object?>{
      'encoding_version': transcriptHashEncodingVersion,
      'conversation_id': conversationId,
      'session_start_seconds': sessionStartSeconds,
      'saved_at_millis': _nextSavedAtMillis(),
      'segments': segments.map(_segmentToJson).toList(),
    };
    await tmp.writeAsString(jsonEncode(payload));
    if (await file.exists()) {
      await file.delete();
    }
    await tmp.rename(file.path);
  }

  Future<List<LocalDraftRecord>> loadDrafts() async {
    if (!enabled) return const [];
    final drafts = await _resolveDraftDirectory();
    final records = <LocalDraftRecord>[];
    for (final file in (await drafts.list().toList()).whereType<File>().where((f) => f.path.endsWith('.json'))) {
      try {
        final decoded = jsonDecode(await file.readAsString());
        if (decoded is! Map<String, dynamic>) continue;
        final conversationId = decoded['conversation_id'];
        if (conversationId is! String || conversationId.isEmpty) continue;
        records.add(
          LocalDraftRecord(
            conversationId: conversationId,
            sessionStartSeconds: decoded['session_start_seconds'] is int ? decoded['session_start_seconds'] as int : 0,
            segments: _segmentsFromPayload(decoded),
          ),
        );
      } catch (_) {
        continue;
      }
    }
    return records;
  }

  Future<void> releaseDraft(String conversationId) async {
    if (!enabled) return;
    final drafts = await _resolveDraftDirectory();
    final file = _fileFor(drafts, conversationId);
    if (await file.exists()) {
      await file.delete();
    }
  }

  Future<Directory> _resolveDraftDirectory() async {
    final dir = await resolveDirectory();
    final drafts = Directory('${dir.path}/$draftFolderName');
    await drafts.create(recursive: true);
    return drafts;
  }

  static Map<String, Object?> _segmentToJson(TranscriptSegment segment) {
    final kept = canonicalizeTranscriptSegment(segment);
    return {
      'id': segment.id,
      'speaker': kept.speaker,
      'speaker_id': kept.speakerId,
      'is_user': kept.isUser,
      'person_id': kept.personId,
      'text': kept.text,
      'start': segment.start,
      'end': segment.end,
    };
  }

  static TranscriptSegment _segmentFromJson(Map<String, dynamic> json) {
    final kept = canonicalizeSegment(
      speaker: json['speaker'] as String?,
      speakerId: json['speaker_id'] as int?,
      isUser: json['is_user'] as bool?,
      personId: json['person_id'] as String?,
      text: json['text'] as String?,
    );
    final segment = TranscriptSegment(
      id: json['id'] as String? ?? '',
      text: kept.text,
      speaker: kept.speaker,
      isUser: kept.isUser,
      personId: kept.personId,
      start: (json['start'] as num?)?.toDouble() ?? 0,
      end: (json['end'] as num?)?.toDouble() ?? 0,
      translations: const [],
    );
    // Constructor re-derives speakerId from the label; restore the stored id
    // so SPEAKER_00 + speaker_id 7 (v5) survives a reload.
    segment.speakerId = kept.speakerId;
    return segment;
  }
}

/// A persisted pending-conversation draft: the live transcript of a recording
/// whose server-side processing has not finished yet.
class LocalDraftRecord {
  const LocalDraftRecord({
    required this.conversationId,
    required this.sessionStartSeconds,
    required this.segments,
  });

  final String conversationId;
  final int sessionStartSeconds;
  final List<TranscriptSegment> segments;
}
