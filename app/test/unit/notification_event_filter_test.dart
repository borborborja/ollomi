import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/notifications/notification_event_filter.dart';

void main() {
  test('conversation completions notify once per conversation', () {
    final data = {'id': 'convo-1', 'title': 'Team standup'};

    expect(
      NotificationEventFilter.shouldNotify(type: 'conversation_completed', data: data, notifiedConversationIds: {}),
      isTrue,
    );
    expect(
      NotificationEventFilter.shouldNotify(
        type: 'conversation_completed',
        data: data,
        notifiedConversationIds: {'convo-1'},
      ),
      isFalse,
    );
  });

  test('conversation completions without an id or title never notify', () {
    expect(
      NotificationEventFilter.shouldNotify(
        type: 'conversation_completed',
        data: {'title': 'No id'},
        notifiedConversationIds: {},
      ),
      isFalse,
    );
    expect(
      NotificationEventFilter.shouldNotify(
        type: 'conversation_completed',
        data: {'id': 'convo-2', 'title': '   '},
        notifiedConversationIds: {},
      ),
      isFalse,
    );
    expect(
      NotificationEventFilter.shouldNotify(
        type: 'conversation_completed',
        data: {'id': 'convo-2'},
        notifiedConversationIds: {},
      ),
      isFalse,
    );
  });

  test('other event types keep notifying', () {
    expect(
      NotificationEventFilter.shouldNotify(type: 'action_item_reminder', data: const {}, notifiedConversationIds: {}),
      isTrue,
    );
  });
}
