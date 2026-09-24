import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

/// The live transcript of a capture the server has not finished processing yet.
///
/// The controller clears its in-memory segments when a recording ends, while
/// the server conversation stays empty until its durable job finishes. Keeping
/// this draft attached to the conversation id lets the Conversations list show
/// what the user just saw and offer the captured audio until the final result
/// lands, so ending a recording never looks like losing data.
class PendingConversationDraft {
  PendingConversationDraft({
    required this.conversationId,
    required this.sessionStartSeconds,
    required this.segments,
    this.photos = const [],
  });

  final String conversationId;
  final int sessionStartSeconds;
  final List<TranscriptSegment> segments;
  final List<ConversationPhoto> photos;

  bool get hasContent => segments.isNotEmpty || photos.isNotEmpty;

  String get previewText => segments.isEmpty ? '' : segments.last.text;
}
