"""worker.py - watches the RAW bucket, transcodes new videos, saves to PROCESSED.

Flow: new file in raw -> download -> ffmpeg (360p, 480p, 720p) -> upload to processed
-> manifest.json last. The client reads the files from the processed storage
(or the CDN in front of it) by itself.

Settings come from environment variables (/etc/video-worker.env).

CDN support:
  When CDN_BASE_URL is set (e.g. https://videos.apkaai.com), URLs written into
  manifest.json point at the Cloudflare edge instead of the raw S3 origin.
"""
import json
import os
import re
import tempfile
import time

import boto3
import redis
from botocore.client import Config
from botocore.exceptions import ClientError

from transcoder import transcode

ENDPOINT = os.environ["S3_ENDPOINT"]
REGION = os.environ.get("S3_REGION", "us-east-1")
RAW = os.environ.get("RAW_BUCKET", "raw")
PROCESSED = os.environ.get("PROCESSED_BUCKET", "processed")
POLL = int(os.environ.get("POLL_SECONDS", "10"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
CDN_BASE_URL = os.environ.get("CDN_BASE_URL", "").rstrip("/")
EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
LOCK_DONE_SECONDS = 6 * 3600
LOCK_RETRY_SECONDS = 600

s3 = boto3.client(
    "s3", endpoint_url=ENDPOINT,
    aws_access_key_id=os.environ["S3_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET"],
    region_name=REGION, config=Config(signature_version="s3v4"),
)
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def log(msg):
    print(msg, flush=True)


def video_id(key):
    """demo.mp4 -> demo ; 'my video.mov' -> my_video"""
    return re.sub(r"[^A-Za-z0-9._-]", "_", key.rsplit(".", 1)[0])


def is_done(vid):
    try:
        s3.head_object(Bucket=PROCESSED, Key=f"{vid}/manifest.json")
        return True
    except ClientError:
        return False


def raw_keys():
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=RAW):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(EXTENSIONS):
                yield obj["Key"]


def process(vid, key):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "source")
        s3.download_file(RAW, key, src)
        files = {}

        def upload(name, path):
            s3_key = f"{vid}/{name}.mp4"
            s3.upload_file(path, PROCESSED, s3_key,
                           ExtraArgs={"ContentType": "video/mp4",
                                      "CacheControl": "public, max-age=31536000, immutable"})
            files[name] = f"{CDN_BASE_URL}/{s3_key}" if CDN_BASE_URL else s3_key
            log(f"  {name} done")

        transcode(src, os.path.join(tmp, "out"), on_done=upload)

        manifest = json.dumps({
            "id": vid,
            "source": key,
            "files": files,
            "cdn": bool(CDN_BASE_URL),
        })
        s3.put_object(Bucket=PROCESSED, Key=f"{vid}/manifest.json",
                      Body=manifest.encode(), ContentType="application/json",
                      CacheControl="public, max-age=60")


def main():
    cdn_info = f"CDN: {CDN_BASE_URL}" if CDN_BASE_URL else "CDN: disabled (direct S3)"
    log(f"Worker watching bucket '{RAW}' every {POLL}s | {cdn_info}")
    while True:
        try:
            for key in raw_keys():
                vid = video_id(key)
                if not r.set(f"lock:{vid}", 1, nx=True, ex=LOCK_DONE_SECONDS):
                    continue                      # already handled or running
                if is_done(vid):
                    continue
                log(f"Processing {key}")
                try:
                    process(vid, key)
                    log(f"Finished {vid}")
                except Exception as e:            # keep the loop alive
                    log(f"Failed {key}: {e}")
                    r.set(f"lock:{vid}", 1, ex=LOCK_RETRY_SECONDS)
        except Exception as e:
            log(f"Loop error: {e}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
