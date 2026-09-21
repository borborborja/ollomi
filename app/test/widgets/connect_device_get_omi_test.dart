import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/capture/connect.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('self-hosted device picker does not open an upstream store', () async {
    Uri? launchedUrl;

    await openOmiStore(
      launcher: (url) async {
        launchedUrl = url;
        return true;
      },
    );
    expect(launchedUrl, isNull);
  });
}
