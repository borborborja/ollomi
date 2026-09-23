import 'dart:async';
import 'package:omi/env/env.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:http/http.dart' as http;

/// Connectivity means the selected server is reachable, even without Internet.
class ConnectivityService {
  static final ConnectivityService _instance = ConnectivityService._internal();
  factory ConnectivityService() => _instance;
  ConnectivityService._internal();
  final _changes = StreamController<bool>.broadcast();
  final _connectivity = Connectivity();
  StreamSubscription? _subscription;
  Timer? _timer;
  bool _checking = false;
  bool _connected = true;
  Stream<bool> get onConnectionChange => _changes.stream;
  bool get isConnected => _connected;

  /// Runs the reachability probe now instead of waiting for the next timer tick.
  Future<void> refresh() => _check();

  Future<void> init() async {
    if (_timer != null) return;
    _subscription = _connectivity.onConnectivityChanged.listen((_) => _check());
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _check());
    await _check();
  }

  Future<void> _check() async {
    if (_checking) return;
    _checking = true;
    final server = Env.apiBaseUrl;
    final client = http.Client();
    var reachable = false;
    try {
      final response = await client.get(Uri.parse('${server}health')).timeout(const Duration(seconds: 3));
      reachable = response.statusCode == 200;
    } catch (_) {
      reachable = false;
    } finally {
      client.close();
      _checking = false;
    }
    if (server != Env.apiBaseUrl) return;
    if (_connected != reachable) {
      _connected = reachable;
      _changes.add(reachable);
    }
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
    _subscription?.cancel();
  }
}
