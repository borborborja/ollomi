import 'dart:async';
import 'dart:convert';
import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/notifications/notification_event_filter.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/utils/notification_channel_strings.dart';

/// Local notifications with a durable authenticated event cursor.
class LocalNotificationService implements NotificationInterface {
  final _notifications = AwesomeNotifications();
  final _messages = StreamController<ServerMessage>.broadcast();
  Timer? _timer;
  bool _polling = false;
  @override Future<void> initialize() async {
    await NotificationChannelStrings.loadAppLocale();
    await _notifications.initialize(null, [NotificationChannel(channelKey: 'channel',
      channelName: NotificationChannelStrings.omiChannelName,
      channelDescription: NotificationChannelStrings.omiChannelDescription)]);
    await listenForMessages();
  }
  @override Future<void> showNotification({required int id, required String title, required String body,
    Map<String, String?>? payload, bool wakeUpScreen = false, NotificationSchedule? schedule,
    NotificationLayout layout = NotificationLayout.Default}) async {
    if (!await _notifications.isNotificationAllowed()) return;
    await _notifications.createNotification(content: NotificationContent(id: id, channelKey: 'channel',
      title: title, body: body, payload: payload, wakeUpScreen: wakeUpScreen, notificationLayout: layout), schedule: schedule);
  }
  @override Future<bool> requestNotificationPermissions() => _notifications.requestPermissionToSendNotifications();
  @override Future<bool> hasNotificationPermissions() => _notifications.isNotificationAllowed();
  @override Future<void> register() => listenForMessages();
  @override Future<String> getTimeZone() async => (await FlutterTimezone.getLocalTimezone()).identifier;
  @override Future<void> saveFcmToken(String? token) async { }
  @override void saveNotificationToken() { unawaited(listenForMessages()); }
  @override Future<void> createNotification({String title = '', String body = '', int notificationId = 1,
    Map<String, String?>? payload}) => showNotification(id: notificationId, title: title, body: body, payload: payload);
  @override void clearNotification(int id) { unawaited(_notifications.cancel(id)); }
  @override Stream<ServerMessage> get listenForServerMessages => _messages.stream;
  @override Future<void> listenForMessages() async {
    _timer ??= Timer.periodic(const Duration(seconds: 30), (_) => _poll());
  }
  Future<void> _poll() async {
    final auth = AuthService.instance;
    if (_polling || !auth.isSignedIn()) return;
    _polling = true;
    final owner = '${auth.instanceId}:${auth.currentUser!.uid}';
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = 'ollomi.events.$owner';
      final notifiedKey = 'ollomi.events.notified.$owner';
      final cursor = prefs.getInt(key) ?? 0;
      final notified = (prefs.getStringList(notifiedKey) ?? const <String>[]).toSet();
      final response = await makeApiCall(url: '${auth.serverUrl}v1/events?after=$cursor', headers: {}, method: 'GET', body: '');
      if (response == null || response.statusCode != 200 || owner != '${auth.instanceId}:${auth.currentUser?.uid}') return;
      final result = jsonDecode(response.body);
      for (final event in result['events']) {
        final type = event['type'] as String? ?? '';
        if (!['action_item_reminder', 'conversation_completed'].contains(type)) continue;
        final data = (event['data'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{};
        if (!NotificationEventFilter.shouldNotify(type: type, data: data, notifiedConversationIds: notified)) continue;
        await showNotification(id: event['id'] % 2147483647, title: 'Ollomi',
          body: data['title'] ?? '', payload: {'conversation_id': data['id']});
        if (type == 'conversation_completed') notified.add(data['id'] as String);
      }
      await prefs.setInt(key, result['cursor']);
      if (notified.isNotEmpty) {
        final ids = notified.toList();
        await prefs.setStringList(notifiedKey, ids.length > 200 ? ids.sublist(ids.length - 200) : ids);
      }
    } catch (_) {
      // Preserve the cursor until delivery succeeds.
    } finally { _polling = false; }
  }
}
NotificationInterface createNotificationService() => LocalNotificationService();
