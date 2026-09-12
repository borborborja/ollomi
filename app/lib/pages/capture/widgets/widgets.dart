import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/widgets/conversation_photo_image.dart';
import 'package:omi/widgets/photos_grid.dart';
import 'package:omi/widgets/transcript.dart';

class PhotosPreviewWidget extends StatelessWidget {
  final List<ConversationPhoto> photos;
  final String? conversationId;
  const PhotosPreviewWidget({super.key, required this.photos, this.conversationId});

  @override
  Widget build(BuildContext context) {
    // Show the last 3 photos, newest first.
    final displayPhotos = photos.length > 3 ? photos.sublist(photos.length - 3) : photos;
    final resolvedConversationId = conversationId ?? context.read<CaptureProvider>().topConversationId;
    return SizedBox(
      height: 80,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: displayPhotos.reversed.map((photo) {
          return Flexible(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2.0),
              child: AspectRatio(
                aspectRatio: 800 / 600,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8.0),
                  child: ConversationPhotoImage(
                    photo: photo,
                    conversationId: resolvedConversationId,
                    fit: BoxFit.cover,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

getTranscriptWidget(
  bool conversationCreating,
  List<TranscriptSegment> segments,
  List<ConversationPhoto> photos,
  BtDevice? btDevice, {
  bool horizontalMargin = true,
  bool topMargin = true,
  bool canDisplaySeconds = true,
  bool isConversationDetail = false,
  double bottomMargin = 100.0,
  Function(String, int)? editSegment,
  Map<String, SpeakerLabelSuggestionEvent> suggestions = const {},
  List<String> taggingSegmentIds = const [],
  Function(SpeakerLabelSuggestionEvent)? onAcceptSuggestion,
  String searchQuery = '',
  int currentResultIndex = -1,
  VoidCallback? onTapWhenSearchEmpty,
  Function(TranscriptSegment)? onSegmentTap,
  Function(int)? onEditSegmentText,
  Key? transcriptKey,
  bool followLatest = false,
  String? conversationId,
  TranscriptScrollState? scrollState,
  double jumpToLatestButtonBottom = 16,
  int contentVersion = 0,
  String layoutIdentity = 'transcript',
  List<Widget> leadingItems = const [],
  List<String> leadingItemIds = const [],
  TranscriptSegmentBuilder? segmentBuilder,
}) {
  if (conversationCreating) {
    return const Padding(
      padding: EdgeInsets.only(top: 80),
      child: Center(child: CircularProgressIndicator(color: Colors.white)),
    );
  }

  final bool showPhotos = photos.isNotEmpty;
  final bool showTranscript = segments.isNotEmpty;

  Widget buildPhotos() {
    return PhotosGridComponent(photos: photos, conversationId: conversationId);
  }

  Widget buildTranscriptSegments() {
    return TranscriptWidget(
      key: transcriptKey,
      segments: segments,
      horizontalMargin: horizontalMargin,
      topMargin: topMargin,
      canDisplaySeconds: canDisplaySeconds,
      isConversationDetail: isConversationDetail,
      bottomMargin: bottomMargin,
      editSegment: editSegment,
      suggestions: suggestions,
      taggingSegmentIds: taggingSegmentIds,
      onAcceptSuggestion: onAcceptSuggestion,
      searchQuery: searchQuery,
      currentResultIndex: currentResultIndex,
      onTapWhenSearchEmpty: onTapWhenSearchEmpty,
      onSegmentTap: onSegmentTap,
      onEditSegmentText: onEditSegmentText,
      followLatest: followLatest,
      scrollState: scrollState,
      jumpToLatestButtonBottom: jumpToLatestButtonBottom,
      contentVersion: contentVersion,
      layoutIdentity: layoutIdentity,
      leadingItems: leadingItems,
      leadingItemIds: leadingItemIds,
      segmentBuilder: segmentBuilder,
    );
  }

  if (showPhotos && showTranscript) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(height: 250, child: buildPhotos()),
        Expanded(child: buildTranscriptSegments()),
      ],
    );
  }

  if (showPhotos) {
    return buildPhotos();
  }

  if (showTranscript) {
    return buildTranscriptSegments();
  }
  return const SizedBox.shrink();
}

getLiteTranscriptWidget(List<TranscriptSegment> segments, List<ConversationPhoto> photos, BtDevice? btDevice) {
  return Column(
    children: [
      if (photos.isNotEmpty) PhotosPreviewWidget(photos: photos),
      if (photos.isNotEmpty && segments.isNotEmpty) const SizedBox(height: 8),
      if (segments.isNotEmpty) LiteTranscriptWidget(segments: segments),
    ],
  );
}
