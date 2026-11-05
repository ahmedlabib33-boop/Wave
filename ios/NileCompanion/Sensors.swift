import ARKit
import AVFoundation
import CoreLocation
import CoreMotion
import Foundation
import SwiftUI

final class LocationSensor: NSObject, ObservableObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    @Published var location: CLLocation?
    @Published var heading: CLHeading?
    @Published var error = ""
    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
    }
    func request() {
        switch manager.authorizationStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse:
            manager.requestLocation()
            if CLLocationManager.headingAvailable() { manager.startUpdatingHeading() }
        default: error = "Location permission is not available. Enable it in Settings."
        }
    }
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if manager.authorizationStatus == .authorizedWhenInUse || manager.authorizationStatus == .authorizedAlways {
            manager.requestLocation()
        }
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        DispatchQueue.main.async { self.location = locations.last; self.error = "" }
        manager.stopUpdatingHeading()
    }
    func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        DispatchQueue.main.async { self.heading = newHeading }
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        DispatchQueue.main.async { self.error = error.localizedDescription }
    }
    func observation() throws -> [String: Any] {
        guard let location, location.horizontalAccuracy >= 0,
              abs(location.timestamp.timeIntervalSinceNow) <= 30 else {
            throw HubError.message("Get a valid GPS reading less than 30 seconds old first.")
        }
        let compass: Any = heading.flatMap { $0.headingAccuracy >= 0 && $0.trueHeading >= 0 ? $0.trueHeading : nil } as Any? ?? NSNull()
        return ["source_id": "phone", "source_type": "phone", "object_type": "device",
                "latitude": location.coordinate.latitude, "longitude": location.coordinate.longitude,
                "altitude": location.verticalAccuracy >= 0 ? location.ellipsoidalAltitude as Any : NSNull(),
                "location_accuracy_m": location.horizontalAccuracy,
                "speed_mps": location.speed >= 0 ? location.speed as Any : NSNull(),
                "heading_deg": location.course >= 0 ? location.course as Any : NSNull(),
                "observed_at": HubClient.timestamp(location.timestamp), "measurement_method": "device_location",
                "details": ["altitude_basis": "WGS84 ellipsoid", "device_true_heading_deg": compass,
                            "speed_accuracy_mps": location.speedAccuracy >= 0 ? location.speedAccuracy as Any : NSNull(),
                            "note": "Device location, not a detected remote object"]]
    }
}

final class DepthSensor: ObservableObject {
    let session = ARSession()
    @Published var running = false
    @Published var error = ""
    func start() async {
        guard ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) else {
            await MainActor.run { error = "ARKit scene depth is unavailable on this device." }; return
        }
        guard await AVCaptureDevice.requestAccess(for: .video) else {
            await MainActor.run { error = "Camera permission is required for depth." }; return
        }
        await MainActor.run {
            let configuration = ARWorldTrackingConfiguration()
            configuration.frameSemantics = .sceneDepth
            session.run(configuration, options: [.resetTracking])
            running = true; error = ""
        }
    }
    func stop() { session.pause(); running = false }
    func observation() throws -> [String: Any] {
        guard let frame = session.currentFrame, let depth = frame.sceneDepth else {
            throw HubError.message("Start the depth session and wait for a valid frame.")
        }
        let buffer = depth.depthMap
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        guard let address = CVPixelBufferGetBaseAddress(buffer) else { throw HubError.message("No depth buffer.") }
        let x = CVPixelBufferGetWidth(buffer) / 2, y = CVPixelBufferGetHeight(buffer) / 2
        let row = address.advanced(by: y * CVPixelBufferGetBytesPerRow(buffer)).assumingMemoryBound(to: Float32.self)
        let metres = row[x]
        guard metres.isFinite, metres > 0, metres <= 5 else {
            throw HubError.message("Center depth is invalid or outside this app's 5 m short-range limit.")
        }
        return ["source_id": "phone", "source_type": "phone", "object_type": "depth_sample",
                "latitude": NSNull(), "longitude": NSNull(), "confidence": NSNull(),
                "observed_at": HubClient.timestamp(Date()), "measurement_method": "direct_measurement",
                "details": ["center_depth_m": metres, "depth_axis": "camera optical Z, not slant range",
                            "arkit_frame_timestamp_s": frame.timestamp, "timestamp_basis": "Native frame read time",
                            "note": "Center surface depth; no object identity, geographic position or long-range capability"]]
    }
}

final class MotionSensor: ObservableObject {
    private let manager = CMMotionManager()
    func start() {
        if manager.isDeviceMotionAvailable {
            manager.deviceMotionUpdateInterval = 0.2
            manager.startDeviceMotionUpdates(using: .xArbitraryZVertical)
        }
    }
    func stop() { manager.stopDeviceMotionUpdates() }
    var orientation: [String: Any]? {
        guard let motion = manager.deviceMotion else { return nil }
        let q = motion.attitude.quaternion
        return ["quaternion_xyzw": [q.x, q.y, q.z, q.w], "frame": "xArbitraryZVertical",
                "timestamp_monotonic_s": motion.timestamp]
    }
}

struct DepthView: UIViewRepresentable {
    let sensor: DepthSensor
    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView(frame: .zero)
        view.session = sensor.session
        return view
    }
    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}
