"""storage_tool.py - helper to test the storage and upload videos.

    vp-storage check
    vp-storage upload ~/demo.mp4
    vp-storage list
"""
import os
import sys

import boto3
from botocore.client import Config

RAW = os.environ.get("RAW_BUCKET", "raw")
PROCESSED = os.environ.get("PROCESSED_BUCKET", "processed")

s3 = boto3.client(
    "s3", endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET"],
    region_name=os.environ.get("S3_REGION", "us-east-1"),
    config=Config(signature_version="s3v4"),
)


def list_bucket(name, limit=50):
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=name):
        for o in page.get("Contents", []):
            print(f"  {name}/{o['Key']}  ({o['Size']} bytes)")
            n += 1
            if n >= limit:
                return
    if n == 0:
        print(f"  {name}: (empty)")


def check():
    # write -> list -> read -> delete in the raw bucket
    key = "_vp_check.txt"
    s3.put_object(Bucket=RAW, Key=key, Body=b"ok")
    keys = [o["Key"] for p in s3.get_paginator("list_objects_v2").paginate(Bucket=RAW)
            for o in p.get("Contents", [])]
    assert key in keys, "upload worked but the listing does not show the file"
    assert s3.get_object(Bucket=RAW, Key=key)["Body"].read() == b"ok"
    s3.delete_object(Bucket=RAW, Key=key)
    s3.head_bucket(Bucket=PROCESSED)
    print(f"OK: can write, list, read and delete in '{RAW}'; '{PROCESSED}' is reachable.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        check()
    elif cmd == "upload" and len(sys.argv) == 3:
        path = sys.argv[2]
        key = os.path.basename(path)
        s3.upload_file(path, RAW, key)
        print(f"Uploaded {path} -> {RAW}/{key}  (video id: {key.rsplit('.', 1)[0]})")
    elif cmd == "list":
        list_bucket(RAW)
        list_bucket(PROCESSED)
    else:
        sys.exit("usage: vp-storage check | upload <file> | list")


if __name__ == "__main__":
    main()
