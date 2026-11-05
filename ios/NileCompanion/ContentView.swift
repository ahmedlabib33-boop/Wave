import SwiftUI

struct ContentView: View {
    @AppStorage("hub_url") private var url = ""
    @State private var token = TokenStore.load()
    @State private var status = ""
    @State private var busy = false
    @StateObject private var gps = LocationSensor()
    @StateObject private var depth = DepthSensor()
    @StateObject private var motion = MotionSensor()
    private var hub: HubClient { HubClient(baseURL: url, token: token) }
    var body: some View {
        NavigationStack {
            Form {
                Section("Your hub") {
                    TextField("https://your-hub.example/", text: $url).textInputAutocapitalization(.never).keyboardType(.URL)
                    SecureField("Access token", text: $token).textInputAutocapitalization(.never)
                        .onChange(of: token) { _, value in TokenStore.save(value) }
                    Text("Keys stay in this device's Keychain. Only manually selected sensor readings are sent.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("GPS · device position") {
                    Button("Get location") { gps.request() }
                    if let location = gps.location {
                        Text("\(location.coordinate.latitude), \(location.coordinate.longitude)").font(.caption.monospaced())
                        Text("Horizontal accuracy: \(location.horizontalAccuracy, specifier: "%.1f") m")
                    }
                    if !gps.error.isEmpty { Text(gps.error).font(.caption) }
                    Button("Send current device location") { send { try gps.observation() } }.disabled(busy)
                }
                Section("LiDAR · local scene depth") {
                    Text("Approximately 5 m local depth. This is not a 5 km radar and does not locate remote objects.")
                        .font(.caption).foregroundStyle(.secondary)
                    if depth.running { DepthView(sensor: depth).frame(height: 220).clipShape(RoundedRectangle(cornerRadius: 8)) }
                    Button(depth.running ? "Stop depth camera" : "Start depth camera") {
                        if depth.running { depth.stop() } else { Task { await depth.start() } }
                    }
                    if !depth.error.isEmpty { Text(depth.error).font(.caption) }
                    Button("Send center depth sample") { send { try depth.observation() } }.disabled(!depth.running || busy)
                }
                Section("Device orientation") {
                    Button("Start orientation readings") { motion.start() }
                    Button("Stop orientation readings") { motion.stop() }
                    Text("Orientation is included in manually sent readings when available. It is not a remote object's heading.").font(.caption)
                }
                if !status.isEmpty { Section("Status") { Text(status) } }
            }.navigationTitle("Nile Observer")
        }.tint(.primary).onDisappear { depth.stop(); motion.stop() }
    }
    private func send(_ build: () throws -> [String: Any]) {
        do {
            var observation = try build()
            if let orientation = motion.orientation {
                var details = observation["details"] as? [String: Any] ?? [:]
                details["device_orientation"] = orientation
                observation["details"] = details
            }
            busy = true
            Task {
                do { try await hub.send(observation); status = "Observation accepted by your hub." }
                catch { status = error.localizedDescription }
                busy = false
            }
        } catch { status = error.localizedDescription }
    }
}
