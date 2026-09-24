import 'dart:async';

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Play/pause control for the audio of a conversation the server is still
/// processing.
///
/// The original recording is published as a signed URL as soon as the capture
/// stops, before the transcript and summary finish. Offering playback here
/// means the user can always verify that what they just recorded is safe.
/// The player is created lazily so building the card never touches platform
/// channels.
class DraftAudioPlayback extends StatefulWidget {
  const DraftAudioPlayback({super.key, required this.conversationId, this.compact = false});

  final String conversationId;

  /// Compact mode renders just the play button (used inside list cards).
  final bool compact;

  @override
  State<DraftAudioPlayback> createState() => _DraftAudioPlaybackState();
}

class _DraftAudioPlaybackState extends State<DraftAudioPlayback> {
  AudioPlayer? _player;
  StreamSubscription<PlayerState>? _playerStateSubscription;
  List<String> _urls = const [];
  int _nextIndex = 0;
  bool _loading = false;

  Future<void> _toggle() async {
    if (_loading) return;
    setState(() => _loading = true);
    try {
      if (_urls.isEmpty) {
        await _loadUrls();
        if (_urls.isEmpty) {
          if (mounted) AppSnackbar.showSnackbarError(context.l10n.audioPlaybackUnavailable);
          return;
        }
      }
      final player = _ensurePlayer();
      if (player.playing) {
        await player.pause();
      } else {
        if (player.audioSource == null) {
          await player.setUrl(_urls[_nextIndex]);
        }
        await player.play();
      }
    } catch (error) {
      Logger.debug('DraftAudioPlayback: $error');
      if (mounted) AppSnackbar.showSnackbarError(context.l10n.audioPlaybackFailed);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadUrls() async {
    for (var attempt = 0; attempt < 4; attempt++) {
      final response = await getConversationAudioSignedUrls(widget.conversationId);
      final urls = response.files.where((file) => file.isCached).map((file) => file.signedUrl!).toList();
      if (urls.isNotEmpty) {
        _urls = urls;
        _nextIndex = 0;
        return;
      }
      await Future<void>.delayed(const Duration(seconds: 2));
    }
  }

  AudioPlayer _ensurePlayer() {
    final existing = _player;
    if (existing != null) return existing;
    final player = AudioPlayer();
    _player = player;
    _playerStateSubscription = player.playerStateStream.listen((state) {
      if (state.processingState == ProcessingState.completed && mounted) {
        unawaited(_playNext());
      }
    });
    return player;
  }

  Future<void> _playNext() async {
    _nextIndex++;
    if (_nextIndex >= _urls.length) {
      _nextIndex = 0;
      await _player?.stop();
      if (mounted) setState(() {});
      return;
    }
    await _player?.setUrl(_urls[_nextIndex]);
    await _player?.play();
  }

  @override
  void dispose() {
    _playerStateSubscription?.cancel();
    _player?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          key: const Key('draft_audio_play_button'),
          onPressed: _loading ? null : _toggle,
          iconSize: widget.compact ? 22 : 28,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
          tooltip: context.l10n.play,
          icon: _loading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : StreamBuilder<PlayerState>(
                  stream: _player?.playerStateStream,
                  builder: (context, snapshot) {
                    final playing = snapshot.data?.playing ?? false;
                    return Icon(playing ? Icons.pause_rounded : Icons.play_arrow_rounded, color: Colors.white);
                  },
                ),
        ),
        if (!widget.compact)
          Expanded(
            child: StreamBuilder<Duration>(
              stream: _player?.positionStream,
              builder: (context, snapshot) {
                final total = _player?.duration?.inMilliseconds ?? 0;
                final position = snapshot.data?.inMilliseconds ?? 0;
                final value = total > 0 ? (position / total).clamp(0.0, 1.0) : 0.0;
                return LinearProgressIndicator(
                  value: value,
                  minHeight: 3,
                  backgroundColor: const Color(0xFF2A2A32),
                  color: Colors.white,
                );
              },
            ),
          ),
      ],
    );
  }
}
