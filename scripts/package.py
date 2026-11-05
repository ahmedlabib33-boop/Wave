"""Create a reviewable source package; exclude credentials, runtime data, traces and dependencies."""

from pathlib import Path
import hashlib
import json
import os
import zipfile

root = Path(__file__).resolve().parents[1]
output = root.parent / "nile-observer.zip"
excluded = {
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    "data",
    "test-results",
    "playwright-report",
}
evidence = {
    "verify_sources.py",
    "verification.json",
    "followup.json",
    "final-source-checks.json",
    "adsb_cairo.json",
    "asf_cairo.json",
    "asf_reference.json",
    "copernicus_cairo.json",
    "umbra_stac.json",
    "umbra-search.json",
    "runtime-scenes.json",
    "model-inference.json",
    "camera-e2e.json",
    "camera-processing-e2e.json",
    "tests-initial.txt",
    "tests-initial.xml",
    "tests-final.txt",
    "tests-final.xml",
    "live-tests.txt",
    "live-tests.xml",
    "transaction-before.txt",
    "transaction-after.txt",
    "browser-initial.txt",
    "browser-final.txt",
    "browser-production.txt",
    "browser-results.json",
    "build-final.txt",
    "lint-final.txt",
    "docker-build-final.log",
    "compose-e2e.txt",
    "compose-health.json",
    "postgis-migrations.txt",
    "operational-status.json",
    "package-smoke.txt",
}
files = []
for folder, dirs, names in os.walk(root):
    dirs[:] = [d for d in dirs if d not in excluded and not d.endswith(".egg-info")]
    for name in names:
        path = Path(folder) / name
        rel = path.relative_to(root)
        if name == ".env" or name.endswith((".pyc", ".tsbuildinfo")):
            continue
        if rel.parts[0] == "research" and not (name in evidence or "screenshots" in rel.parts):
            continue
        files.append((path, rel))
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path, rel in sorted(files):
        archive.write(path, Path(root.name) / rel)
with zipfile.ZipFile(output) as archive:
    bad = archive.testzip()
    assert bad is None, bad
    assert not any("/.env" == n[-5:] or "/data/" in n or "/node_modules/" in n for n in archive.namelist())
manifest = {
    "archive": output.name,
    "bytes": output.stat().st_size,
    "files": len(files),
    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "excludes": "Credentials, runtime databases, installed dependencies and browser traces",
}
(output.with_suffix(".zip.json")).write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
