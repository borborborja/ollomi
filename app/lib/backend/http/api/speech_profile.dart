import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/device_speech_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<bool> userHasSpeakerProfile() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return true;
  Logger.debug('userHasSpeakerProfile: ${response.body}');
  if (response.statusCode == 200) {
    try {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      // A server without a configured voiceprint service cannot enroll the
      // user. Treat it as complete so onboarding does not lead to a failing
      // recording flow; the server controls this capability through .env.
      return data['available'] != true || data['has_profile'] == true;
    } catch (e) {
      Logger.debug('Failed to parse userHasSpeakerProfile response: $e');
      return true;
    }
  }
  return true; // to avoid showing the banner if the request fails or there's no internet.
}

/// Pre-flight check before entering the recording UI, so a known-down
/// streaming primary surfaces as an upfront error dialog instead of a dead
/// recording screen with no questions/progress ever arriving.
Future<bool> isSttAvailable() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile/stt-availability',
    headers: {},
    method: 'GET',
    body: '',
  );
  // Fail open: a hiccup on the check itself shouldn't block a working flow —
  // the existing STT_UNAVAILABLE detection after repeated failed connects is
  // still the real safety net.
  if (response == null) return true;
  if (response.statusCode == 200) {
    try {
      return wire.GeneratedSttAvailabilityResponse.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      ).available;
    } catch (e) {
      Logger.debug('Failed to parse isSttAvailable response: $e');
      return true;
    }
  }
  return true;
}

Future<String?> getUserSpeechProfile() async {
  // Ollomi persists an encrypted embedding, never raw enrollment audio, so
  // there is intentionally no playback URL.
  return null;
}

Future<bool> uploadProfile(File file) async {
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/speech-profile',
      files: [file],
      fileFieldName: 'file',
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['has_profile'] == true;
    } else {
      Logger.debug(
        'Failed to upload sample. Status code: ${response.statusCode} body: ${response.body}',
      );
      throw Exception(
        'Failed to upload sample (${response.statusCode}): ${response.body}',
      );
    }
  } catch (e) {
    Logger.debug('An error occurred uploadSample: $e');
    throw Exception('An error occurred uploadSample: $e');
  }
}

Future<List<String>> getExpandedProfileSamples() async {
  // Ollomi does not retain enrollment recordings, so there are no expandable
  // samples to list or play back.
  return [];
}

Future<bool> deleteProfileSample(
  String conversationId,
  int segmentIdx, {
  String? personId,
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('deleteProfileSample: ${response.body}');
  if (response.statusCode == 200) {
    try {
      return (jsonDecode(response.body) as Map<String, dynamic>)['status'] == 'ok';
    } catch (e) {
      Logger.debug('Failed to parse deleteProfileSample response: $e');
      return false;
    }
  }
  return false;
}
