# Optional iPhone companion

Native SwiftUI / ARKit / CoreLocation / CoreMotion **source is provided; it has not been compiled, signed or run on an iPhone in this Linux environment**. The web PWA is separately validated with an iPhone-sized WebKit profile.

On macOS with Xcode and XcodeGen:

```bash
cd ios
xcodegen generate
open NileCompanion.xcodeproj
```

Choose a development signing team, connect a physical iPhone 15 Pro Max, and build the app. A personal development account may be sufficient for local device testing; signing and distribution rules belong to Apple. No account, subscription or hardware is purchased by this project. iOS 17 is the deployment minimum. A simulator cannot establish physical LiDAR operation.

Enter your own **HTTPS** hub URL and the hub token. GPS observations use the built-in `phone` source, `CLLocation.timestamp`, measured horizontal accuracy, and available speed/course. An invalid or older-than-30-second GPS sample is refused. Device compass/orientation data stays explicitly separate from an object's motion heading. Device-relative CoreMotion quaternions do not become map bearings.

The camera button starts an ARKit `sceneDepth` session only on supported hardware and after camera permission. Send center depth samples manually. Depth is optical-axis Z distance, not a guaranteed slant range or classified object. Readings outside this application's short-range 0–5 m validation window are rejected. Geographic coordinates and model confidence remain null. Neither RGB images nor complete depth maps are uploaded. The token is stored in Keychain and never in a URL.

Supported source code paths: GPS, short-range depth, optional device orientation, manual authenticated upload. **Not implemented:** Nearby Interaction pairing, compatible UWB accessory protocol, Bluetooth sensor app integration, microphone localization, background sensor streaming, Arabic native UI, or automatic camera-object geolocation. Nearby Interaction requires a supported peer/accessory and exchanged discovery/session configuration; it is not a generic radar. A PWA cannot substitute for these native frameworks.

Framework references were checked against Apple's public documentation: [ARKit depth](https://developer.apple.com/documentation/arkit/ardepthdata), [Nearby Interaction](https://developer.apple.com/documentation/nearbyinteraction), [Core Location](https://developer.apple.com/documentation/corelocation), [Core Motion](https://developer.apple.com/documentation/coremotion).
