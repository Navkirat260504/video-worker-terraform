"""zoom_webhook.py — Receives Zoom recording.completed webhooks and uploads
the MP4 recording to the careerlauncher-raw S3 bucket.

Flow:
  Zoom meeting ends
    → Zoom POST /webhook  (recording.completed event)
    → Validate HMAC signature
    → Download each MP4 recording from Zoom's download URL
    → Upload to RAW_BUCKET/<meeting_topic>_<meeting_id>_<start_time>.mp4
    → Worker picks it up and transcodes

Environment variables (from /etc/zoom-webhook.env):
  ZOOM_WEBHOOK_SECRET  — secret token from Zoom Marketplace app
  ZOOM_WEBHOOK_PORT    — port to listen on (default 8080)
  S3_ENDPOINT, S3_REGION, S3_KEY, S3_SECRET, RAW_BUCKET
    — same S3 credentials used by the worker
"""

import hashlib
import hmac
import json
import logging
import os
import re
import tempfile
import threading

import boto3
import requests
from botocore.client import Config
from flask import Flask, jsonify, request

# ── Config ────────────────────────────────────────────────────────────────────
WEBHOOK_SECRET = os.environ["ZOOM_WEBHOOK_SECRET"]
PORT           = int(os.environ.get("ZOOM_WEBHOOK_PORT", "8080"))
S3_ENDPOINT    = os.environ["S3_ENDPOINT"]
S3_REGION      = os.environ.get("S3_REGION", "us-east-1")
S3_KEY         = os.environ["S3_KEY"]
S3_SECRET      = os.environ["S3_SECRET"]
RAW_BUCKET     = os.environ.get("RAW_BUCKET", "raw")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("zoom-webhook")

# ── S3 client ─────────────────────────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_KEY,
    aws_secret_access_key=S3_SECRET,
    region_name=S3_REGION,
    config=Config(signature_version="s3v4"),
)

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_name(text):
    """Make a string safe for use as an S3 key component."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", text.strip())


def verify_signature(request) -> bool:
    """Validate Zoom webhook signature (v1 HMAC-SHA256)."""
    msg_id        = request.headers.get("x-zm-request-timestamp", "")
    msg_signature = request.headers.get("x-zm-signature", "")
    body          = request.get_data(as_text=True)

    message   = f"v0:{msg_id}:{body}"
    expected  = "v0=" + hmac.new(
        WEBHOOK_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, msg_signature)


def download_and_upload(recording, s3_key):
    """Download a single recording file from Zoom and upload to S3."""
    download_url = recording.get("download_url")
    if not download_url:
        log.warning("No download_url in recording object")
        return

    log.info(f"Downloading {s3_key} from Zoom...")
    with tempfile.TemporaryDirectory() as tmp:
        local_path = os.path.join(tmp, "recording.mp4")

        # Zoom requires the access_token appended for server-to-server downloads
        with requests.get(download_url, stream=True, timeout=3600) as resp:
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)

        file_size = os.path.getsize(local_path)
        log.info(f"Downloaded {file_size / 1024 / 1024:.1f} MB — uploading to S3...")

        s3.upload_file(
            local_path, RAW_BUCKET, s3_key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        log.info(f"Uploaded to s3://{RAW_BUCKET}/{s3_key}")


def handle_recording(payload):
    """Process recording.completed event in a background thread."""
    object_data = payload.get("object", {})
    topic       = safe_name(object_data.get("topic", "untitled"))
    meeting_id  = str(object_data.get("id", "unknown"))
    start_time  = safe_name(object_data.get("start_time", "")[:19])  # 2026-11-05T10:00:00

    recording_files = object_data.get("recording_files", [])
    mp4_files = [
        f for f in recording_files
        if f.get("file_type", "").upper() == "MP4"
        and f.get("status", "") == "completed"
    ]

    if not mp4_files:
        log.warning("No completed MP4 files in recording.completed payload")
        return

    for i, rec in enumerate(mp4_files):
        suffix = f"_{i}" if len(mp4_files) > 1 else ""
        s3_key = f"{topic}_{meeting_id}_{start_time}{suffix}.mp4"
        t = threading.Thread(
            target=download_and_upload, args=(rec, s3_key), daemon=True
        )
        t.start()
        log.info(f"Started upload thread for {s3_key}")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Zoom pre-validates with a GET request
    if request.method == "GET":
        return jsonify({"status": "ok"}), 200

    # 1. Verify signature
    if not verify_signature(request):
        log.warning("Signature verification failed")
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(force=True, silent=True) or {}
    event   = payload.get("event", "")
    log.info(f"Received event: {event}")

    # 2. Zoom URL validation challenge (required when setting up webhook)
    if event == "endpoint.url_validation":
        plain_token   = payload.get("payload", {}).get("plainToken", "")
        hashed_token  = hmac.new(
            WEBHOOK_SECRET.encode(), plain_token.encode(), hashlib.sha256
        ).hexdigest()
        return jsonify({"plainToken": plain_token, "encryptedToken": hashed_token})

    # 3. Recording completed
    if event == "recording.completed":
        threading.Thread(
            target=handle_recording,
            args=(payload.get("payload", {}),),
            daemon=True,
        ).start()
        return jsonify({"status": "accepted"}), 200

    # 4. All other events — acknowledge and ignore
    return jsonify({"status": "ignored"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bucket": RAW_BUCKET}), 200


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info(f"Zoom webhook server starting on port {PORT}")
    log.info(f"Raw bucket: {RAW_BUCKET}")
    app.run(host="0.0.0.0", port=PORT)
