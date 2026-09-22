import Foundation
import SwiftWhisper

/// Local Whisper wrapper for an explicitly downloaded model.
public final class OmiWhisperTranscriber {
  private let whisper: Whisper?

  public init(modelURL: URL? = nil) {
    if let modelURL {
      whisper = Whisper(fromFileURL: modelURL)
    } else {
      whisper = nil
    }
  }

  public func transcribe(audioFrames: [Float]) async throws -> String {
    guard let whisper else {
      throw NSError(
        domain: "omi.stt.whisper", code: 1, userInfo: [NSLocalizedDescriptionKey: "Whisper model not loaded"])
    }
    let segments = try await whisper.transcribe(audioFrames: audioFrames)
    return segments.map(\.text).joined()
  }
}
