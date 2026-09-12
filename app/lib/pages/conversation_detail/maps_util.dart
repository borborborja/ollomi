import 'package:map_launcher/map_launcher.dart';
import 'package:url_launcher/url_launcher.dart';
class MapsUtil {
  static String getGoogleMapsPlaceUrl(String placeId) => '';
  static void launchMap(double lat, double lng) async {
    final installed = await MapLauncher.installedMaps;
    if (installed.isNotEmpty) {
      await installed.first.showMarker(coords: Coords(lat,lng),title:'');
      return;
    }
    final uri = Uri.parse('geo:$lat,$lng?q=$lat,$lng');
    if (await canLaunchUrl(uri)) await launchUrl(uri,mode:LaunchMode.externalApplication);
  }
}
