# Selected upstream repository review

The addendum referenced eight repositories but did not supply their URLs. The follow-up clarified that repositories are optional building blocks and that the best compatible components may be selected. The eight projects below are an **explicit engineering review set**, not a claimed reconstruction of an unseen second prompt. All were checked through public GitHub metadata and current default-branch commit references; relevant README or dependency files were read without executing repository instructions.

The app stays one project. The decision is to retain its functional **OpenCV + YOLOX** stack and add a lightweight **Frigate event compatibility layer**. None of the other repositories is automatically installed, cloned into the application, or treated as a source of public camera access.

| Repository | Verified commit | License reported by GitHub | Relevant capability / decision |
|---|---|---|---|
| [OpenCV](https://github.com/opencv/opencv) | `7c1e0d5d503bd8e6e54b07d828d32ce028f8869e` | Apache-2.0 | Retain the installed validated 4.x decoding/image-processing component. The reviewed upstream default is 5.x; this review does not upgrade the runtime. |
| [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) | `6ddff4824372906469a7fae2dc3206c7aa4bbaee` | Apache-2.0 | Retain the already tested ONNX detector/nano model. Its existing weight hash, license and source provenance remain intact. |
| [Frigate](https://github.com/blakeblackshear/frigate) | `1cb5ec4107089b1dfe106b08a2c5fa7e93170ab3` | MIT | Add documented event normalization for authorized mapped cameras over REST/MQTT. Do not replace the hub or install another NVR. Frigate's trademarks are separate from its code license. |
| [ByteTrack](https://github.com/FoundationVision/ByteTrack) | `d1bf0191adff59bc8fcfeaa0b33d3d1642552a99` | MIT | Candidate tracking benchmark once representative authorized video/ground truth exists. The former `ifzhang/ByteTrack` URL redirects to this canonical repository. Not executed or substituted for the current tracker in this continuation. |
| [Norfair](https://github.com/tryolabs/norfair) | `e517b4236f6b67a6ecf342f5df1fccb7788dbc54` | BSD-3-Clause | Lightweight tracking is relevant, but the reviewed `pyproject.toml` requires NumPy `^1.23.0` on Python ≥3.8. That conflicts with this project's validated `numpy>=2,<3`. No downgrade or forced installation was made. |
| [FilterPy](https://github.com/rlabbe/filterpy) | `5df4e095fac07684a05c495bd72d3424f7c68c9c` | MIT | Useful statistical primitives; not a sensor or a way to infer absent identity/calibration/covariance evidence. Defer cross-source fusion until those prerequisites exist. |
| [Stone Soup](https://github.com/dstl/Stone-Soup) | `e9247a17eef906c3455cd281312e0227dbb79aa9` | MIT | Advanced tracking framework, deferred pending supported sensor models and evaluation data. Current GitHub metadata reports MIT; this corrects the earlier baseline source report's unverified BSD label without erasing that dated report. |
| [python-onvif-zeep](https://github.com/FalkTannhaeuser/python-onvif-zeep) | `d3a2d68b6c3a1c49891da54e5a430f1f6fc83581` | MIT | Useful ONVIF reference. Preserve the existing adapter until an authorized physical device provides a concrete compatibility requirement and regression test. No network/device discovery was run. |

Metadata, timestamps and decisions are recorded in `research/continuation/repository-review.json`; file-access checks are in `research/continuation/upstream/file-checks.json`. The model manifest remains in `models/manifest.json`.

These are compatibility and architectural decisions, **not a benchmark claiming all eight repositories were installed or tested end-to-end**. The existing OpenCV/YOLOX runtime and published test-media path have execution evidence. Frigate normalization has protocol/contract tests but no supplied live NVR. The other projects were reviewed as potential components and deliberately not substituted for working code. No third-party source code or brand assets were copied into the application by this review.

A software repository's code license does not authorize access to a camera, an NVR, private data, a government feed, or unrestricted use of a model/dataset. Public camera availability and permitted detection use remain separate evidence fields in the investigation workflow.
