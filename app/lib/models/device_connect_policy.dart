/// What the app does with capture when this known device becomes the active one.
enum DeviceRecordingOnConnect {
  none('none'),
  continuous('continuous'),
  oneOff('one_off');

  const DeviceRecordingOnConnect(this.storageValue);

  final String storageValue;

  static DeviceRecordingOnConnect fromStorage(String? value) {
    return DeviceRecordingOnConnect.values.firstWhere(
      (option) => option.storageValue == value,
      orElse: () => DeviceRecordingOnConnect.none,
    );
  }
}
