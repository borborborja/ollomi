/// Pure decision for which server events become local notifications.
///
/// The server emits `conversation_completed` once per finished job, so
/// multi-part conversations and explicit reprocessing can emit repeatedly for
/// the same conversation. Only the first completion with a title notifies; the
/// server additionally skips completions for conversations that heard no
/// speech.
class NotificationEventFilter {
  const NotificationEventFilter._();

  static bool shouldNotify({
    required String type,
    required Map<String, dynamic> data,
    required Set<String> notifiedConversationIds,
  }) {
    if (type == 'conversation_completed') {
      final id = data['id'];
      if (id is! String || id.isEmpty) return false;
      if ((data['title'] ?? '').toString().trim().isEmpty) return false;
      return !notifiedConversationIds.contains(id);
    }
    return true;
  }
}
