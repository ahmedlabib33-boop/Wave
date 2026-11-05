import base64
import hashlib
import multiprocessing as mp
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit, urlunsplit
from xml.etree import ElementTree as ET
import httpx
from .config import get_settings


def validate_stream_url(url, allowed_hosts):
    parsed = urlsplit(url)
    allowed = {h.strip().lower() for h in allowed_hosts.split(",") if h.strip()}
    if (
        parsed.scheme not in ("rtsp", "rtsps", "http", "https")
        or not parsed.hostname
        or parsed.hostname.lower() not in allowed
    ):
        raise ValueError("Camera host must be explicitly listed in CAMERA_ALLOWED_HOSTS; http(s)/rtsp(s) only")
    return url


def resolve_onvif(url, allowed_hosts):
    """Use the operator-supplied ONVIF media-service URL. No discovery or network scanning."""
    from xml.sax.saxutils import escape

    parsed = urlsplit(validate_stream_url(url, allowed_hosts))
    clean = urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, parsed.query, ""))
    user, password = unquote(parsed.username or ""), unquote(parsed.password or "")

    def envelope(action):
        nonce = secrets.token_bytes(16)
        created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
        return f"""<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><s:Header><wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><wsse:UsernameToken><wsse:Username>{escape(user)}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password><wsse:Nonce>{base64.b64encode(nonce).decode()}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></s:Header><s:Body>{action}</s:Body></s:Envelope>"""

    def call(action):
        r = httpx.post(
            clean,
            content=envelope(action),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=8,
            auth=httpx.BasicAuth(user, password),
            follow_redirects=False,
        )
        if r.status_code != 200:
            raise ValueError(f"ONVIF media service returned HTTP {r.status_code}")
        return ET.fromstring(r.content)

    profiles = call("<trt:GetProfiles/>").findall(".//{http://www.onvif.org/ver10/media/wsdl}Profiles")
    if not profiles or not profiles[0].get("token"):
        raise ValueError("No ONVIF media profile returned")
    token = escape(profiles[0].get("token"))
    response = call(
        f"<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>{token}</trt:ProfileToken></trt:GetStreamUri>"
    )
    uri = response.findtext(".//{http://www.onvif.org/ver10/schema}Uri")
    if not uri:
        raise ValueError("ONVIF response has no stream URI")
    validate_stream_url(uri, allowed_hosts)
    target = urlsplit(uri)
    if user and not target.username:
        from urllib.parse import quote

        uri = urlunsplit(
            (
                target.scheme,
                f"{quote(user, safe='')}:{quote(password, safe='')}@{target.netloc}",
                target.path,
                target.query,
                target.fragment,
            )
        )
    return uri


def _capture_process(conn, url, protocol, allowed_hosts, max_frames, model_path):
    # OpenCV/FFmpeg may include a credentialed URL in stderr. Suppress it in this isolated reader.
    with open(os.devnull, "w") as null:
        os.dup2(null.fileno(), 2)
    try:
        import cv2
        from .vision import YOLOXDetector, process_frames

        validate_stream_url(url, allowed_hosts)
        if protocol == "onvif":
            url = resolve_onvif(url, allowed_hosts)
        cv2.setNumThreads(1)
        cap = cv2.VideoCapture(
            url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 7000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000]
        )
        if not cap.isOpened():
            raise RuntimeError("Stream could not be opened")
        detector = YOLOXDetector(model_path) if max_frames > 1 else None
        result = process_frames(cap, detector, max_frames)
        cap.release()
        conn.send({"ok": True, **result})
    except Exception as error:
        conn.send(
            {
                "ok": False,
                "error": str(error)[:150] if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__,
            }
        )
    finally:
        conn.close()


def capture_camera(camera, max_frames=1):
    cfg = get_settings()
    url = os.environ.get(camera.url_env)
    if not url:
        raise ValueError(f"Server variable {camera.url_env} is not configured")
    validate_stream_url(url, cfg.camera_allowed_hosts)
    if max_frames > 1 and not cfg.yolox_model_path:
        raise ValueError("YOLOX_MODEL_PATH is not configured; install the documented Apache-2.0 model")
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_capture_process,
        args=(child, url, camera.protocol, cfg.camera_allowed_hosts, max_frames, cfg.yolox_model_path),
    )
    process.start()
    child.close()
    try:
        if not parent.poll(40 if max_frames > 1 else 18):
            raise RuntimeError("Camera read timed out")
        result = parent.recv()
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return result
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=3)
