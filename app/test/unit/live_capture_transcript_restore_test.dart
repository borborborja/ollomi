import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/local_segment_store.dart';

class _OfflineConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

TranscriptSegment _segment(String id, String text) {
  return TranscriptSegment(
    id: id,
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0,
    end: 1,
    translations: const [],
  );
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _OfflineConnectivityPlatform();
  });

  test('processing_started carries the conversation for the processing card', () {
    final event = MessageEvent.fromJson({
      'type': 'processing_started',
      'job_id': 'job-1',
      'memory': {
        'id': 'conv-1',
        'status': 'processing',
        'created_at': '2026-09-24T12:00:00+00:00',
        'started_at': '2026-09-24T12:00:00+00:00',
        'finished_at': '2026-09-24T12:00:00+00:00',
        'structured': {'title': 'Prova'},
      },
    });
    expect(event, isA<ConversationProcessingStartedEvent>());
    expect((event as ConversationProcessingStartedEvent).memory.id, 'conv-1');
  });

  test('processing_started without a conversation stays unknown', () {
    final event = MessageEvent.fromJson({'type': 'processing_started', 'job_id': 'job-1'});
    expect(event, isA<UnknownEvent>());
  });

  test('an empty in-progress conversation never reaches the list', () {
    final provider = CaptureProvider(localSegmentStore: LocalSegmentStore.disabled());
    ServerConversation conversation({
      required ConversationStatus status,
      List<TranscriptSegment> segments = const [],
    }) {
      return ServerConversation(
        id: 'conv-1',
        createdAt: DateTime.now(),
        structured: Structured('', ''),
        status: status,
        transcriptSegments: segments,
      );
    }

    // The device connected but never sent audio: no phantom "Nueva conversación".
    expect(provider.shouldSurfaceConversation(conversation(status: ConversationStatus.in_progress)), isFalse);
    // Once there is content, the live row is real.
    expect(
      provider.shouldSurfaceConversation(
        conversation(status: ConversationStatus.in_progress, segments: [_segment('s1', 'hola')]),
      ),
      isTrue,
    );
    // Terminal states are always visible.
    for (final status in [
      ConversationStatus.processing,
      ConversationStatus.completed,
      ConversationStatus.failed,
    ]) {
      expect(provider.shouldSurfaceConversation(conversation(status: status)), isTrue);
    }
  });

  test('mergeLiveSegments never drops the live transcript', () {
    final provider = CaptureProvider(localSegmentStore: LocalSegmentStore.disabled());
    final live = <TranscriptSegment>[_segment('live-1', 'hola')];
    final server = <TranscriptSegment>[_segment('server-1', 'què tal')];

    final merged = provider.mergeLiveSegments(live, server);
    expect(merged.map((segment) => segment.text), ['hola', 'què tal']);

    // Re-merging the same server view (resume/refresh) must not duplicate.
    provider.mergeLiveSegments(merged, server);
    expect(merged.length, 2);

    // A server segment with the same id replaces the live copy in place.
    final updated = provider.mergeLiveSegments(merged, [_segment('live-1', 'hola!')]);
    expect(updated.where((segment) => segment.id == 'live-1').single.text, 'hola!');
    expect(updated.length, 2);
  });

  test('durable live segments survive and can be released', () async {
    final directory = await Directory.systemTemp.createTemp('ollomi-segments');
    final store = LocalSegmentStore.at(directory);
    final provider = CaptureProvider(localSegmentStore: store);

    await store.replaceSession('live-100', [_segment('s1', 'primera')]);
    await store.replaceSession('live-200', [_segment('s2', 'segona')]);

    final latest = await provider.loadLatestLocalSegments();
    expect(latest.single.text, 'segona');
    expect((await provider.loadLocalSegments('live-100')).single.text, 'primera');

    await provider.releaseLocalSegments('live-100');
    expect(await provider.loadLocalSegments('live-100'), isEmpty);
    await directory.delete(recursive: true);
  });
}
