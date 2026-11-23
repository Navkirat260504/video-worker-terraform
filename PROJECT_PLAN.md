# Video Worker — Project Plan & Architecture

## Overview

A Terraform-managed deployment that installs a video transcoding pipeline on an existing **Utho** cloud server. Raw videos uploaded to an S3-compatible bucket are automatically detected, transcoded into multiple resolutions, and saved to a processed bucket for client consumption (optionally via CDN).

---

## Goals

- Automate deployment of the video worker to any Utho server with a single `terraform apply`
- Transcode uploaded videos to 360p, 480p, and 720p without manual intervention
- Prevent duplicate processing using a local Redis lock
- Keep credentials secure (never in code, stored in a root-only env file on the server)
- Allow the client to set up their own CDN on the processed bucket independently

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Utho Cloud Server                        │
│                                                                 │
│   ┌──────────────┐     ┌──────────────┐     ┌───────────────┐  │
│   │  worker.py   │────▶│transcoder.py │────▶│  ffmpeg CLI   │  │
│   │  (systemd)   │     │  (library)   │     │  360/480/720p │  │
│   └──────┬───────┘     └──────────────┘     └───────────────┘  │
│          │                                                      │
│   ┌──────▼───────┐                                              │
│   │  Redis       │  (dedup / processing lock, 127.0.0.1 only)  │
│   │  localhost   │                                              │
│   └──────────────┘                                              │
└────────────┬────────────────────────────┬───────────────────────┘
             │ poll every N seconds        │ upload renditions
             ▼                             ▼
   ┌──────────────────┐         ┌──────────────────────┐
   │   Raw Bucket     │         │   Processed Bucket   │
   │  (Utho S3)       │         │   (Utho S3) origin   │
   │                  │         │                      │
   │  demo.mp4        │         │  demo/360p.mp4       │
   │  video2.mov      │         │  demo/480p.mp4       │
   │  ...             │         │  demo/720p.mp4       │
   └──────────────────┘         │  demo/manifest.json  │
                                └──────────┬───────────┘
                                           │ origin pull
                                           ▼
                                ┌──────────────────────┐
                                │   Cloudflare CDN     │
                                │  videos.domain.com   │
                                │  CNAME → S3 origin   │
                                │  mp4:  1 year cache  │
                                │  json: 60 sec cache  │
                                └──────────┬───────────┘
                                           │ (cdn_enabled=true)
                                           ▼
                                      End Users
```

---

## Data Flow

```
1. Client uploads video  ──▶  Raw Bucket (e.g. raw/demo.mp4)
2. worker.py polls Raw Bucket every POLL_SECONDS
3. New file found  ──▶  Redis lock acquired (prevents reprocessing)
4. Video downloaded to /tmp (tempfile)
5. transcoder.py calls ffmpeg for each resolution (360p / 480p / 720p)
6. Each rendition uploaded to Processed Bucket as it completes
7. manifest.json written LAST  ──▶  signals all renditions are ready
8. Client reads manifest.json, then streams renditions (or via CDN)
```

---

## Project Structure

```
video-worker-terraform/
├── main.tf                        # Core Terraform resource (SSH deploy)
├── variables.tf                   # All input variables
├── outputs.tf                     # SSH, log, and test commands
├── versions.tf                    # Terraform version constraint (>= 1.4)
├── terraform.tfvars               # Your actual variable values (gitignored)
│
├── app/
│   ├── worker.py                  # Main polling loop + S3 + Redis logic
│   ├── transcoder.py              # ffmpeg wrapper (360p/480p/720p)
│   └── storage_tool.py            # CLI: vp-storage check|upload|list
│
└── templates/
    ├── install.sh.tftpl           # Server bootstrap script (apt, venv, systemd)
    ├── video-worker.env.tftpl     # Env file template (S3 credentials)
    └── video-worker.service.tftpl # systemd unit file template
```

---

## Components

### Terraform Layer

| File | Purpose |
|---|---|
| `main.tf` | SSH connection + file upload + remote-exec provisioners via `terraform_data` |
| `variables.tf` | Declares all inputs (server IP, SSH creds, S3 creds, bucket names) |
| `outputs.tf` | Prints SSH, log-tail, and test-upload commands after apply |
| `versions.tf` | Requires Terraform >= 1.4.0 (needed for `terraform_data`) |

Re-deploy is triggered automatically when any of these change:
- `app/worker.py`, `app/transcoder.py`, `app/storage_tool.py` (file hash)
- The rendered service unit, install script, or env file (content hash)
- `var.server_ip`

### Application Layer

| File | Purpose |
|---|---|
| `worker.py` | Polls raw bucket, acquires Redis lock, calls transcoder, uploads results |
| `transcoder.py` | Runs ffmpeg per resolution; skips upscaling if source is smaller |
| `storage_tool.py` | Manual CLI tool for testing bucket connectivity and uploads |

### Server Setup (install.sh)

Executed once per deploy via `remote-exec`:

1. Create `app_user` Linux user if missing
2. Install `ffmpeg`, `redis-server`, `python3-venv`, `python3-pip` via apt
3. Bind Redis to `127.0.0.1` only
4. Create `/opt/video-pipeline/` with Python venv + `boto3`, `redis`
5. Copy app files to `/opt/video-pipeline/app/`
6. Write `/etc/video-worker.env` (mode 640, root:app_user)
7. Install `vp-storage` wrapper script to `/usr/local/bin/`
8. Install and start `video-worker` systemd service

---

## Input Variables

| Variable | Default | Sensitive | Description |
|---|---|---|---|
| `server_ip` | — | No | Public IP of the Utho instance |
| `ssh_user` | `root` | No | SSH login user (needs sudo) |
| `ssh_password` | `""` | Yes | SSH password (leave empty to use key) |
| `ssh_private_key_path` | `~/.ssh/id_ed25519` | No | Path to SSH private key |
| `app_user` | `deploy` | No | Linux user that runs the worker |
| `s3_endpoint` | — | No | Utho object storage endpoint URL |
| `s3_region` | `us-east-1` | No | Storage region |
| `s3_access_key` | — | Yes | S3 access key |
| `s3_secret_key` | — | Yes | S3 secret key |
| `raw_bucket` | `raw` | No | Bucket for incoming raw videos |
| `processed_bucket` | `processed` | No | Bucket for transcoded output |
| `poll_seconds` | `10` | No | How often the worker polls for new videos |

---

## Outputs

| Output | Value |
|---|---|
| `ssh_command` | SSH into the server |
| `watch_logs` | Tail the worker logs via journalctl |
| `test_upload` | Upload a test video and list bucket contents |

---

## Deployment Steps

### Prerequisites

- Terraform >= 1.4.0 installed locally
- Utho server already running (Ubuntu/Debian recommended)
- Utho S3 buckets (`raw` and `processed`) already created
- SSH access to the server (password or key)

### Deploy

```bash
# 1. Copy and fill in your values
cp terraform.tfvars.example terraform.tfvars   # edit with your server IP, keys, etc.

# 2. Initialise (no provider plugins needed)
terraform init

# 3. Preview changes
terraform plan

# 4. Deploy
terraform apply

# 5. Verify the worker is running
ssh root@<server_ip> 'systemctl status video-worker'

# 6. Test storage connectivity
ssh root@<server_ip> 'sudo vp-storage check'
```

### Re-deploy

Any change to app code or config automatically triggers a re-deploy on the next `terraform apply` (hashes in `triggers_replace` detect the change).

---

`## Security Notes
`
- S3 credentials are marked `sensitive = true` in Terraform — never printed in plan output
- `/etc/video-worker.env` is written with mode `640` (root:app_user) — not world-readable
- Redis is bound to `127.0.0.1` only — not exposed to the network
- The worker runs as a non-root `app_user` (default: `deploy`)
- SSH private key path is never uploaded; only used locally by Terraform

---

## Operational Runbook

### Watch live logs
```bash
ssh root@<server_ip> 'sudo journalctl -u video-worker -f'
```

### Restart the worker
```bash
ssh root@<server_ip> 'sudo systemctl restart video-worker'
```

### Upload a test video manually
```bash
ssh root@<server_ip> 'sudo vp-storage upload ~/demo.mp4'
```

### List bucket contents
```bash
ssh root@<server_ip> 'sudo vp-storage list'
```

### Check storage connectivity
```bash
ssh root@<server_ip> 'sudo vp-storage check'
```

---

## Known Limitations & Future Improvements

| Area | Current State | Possible Improvement |
|---|---|---|
| CDN | Cloudflare CDN implemented (`cdn_enabled = true`) | Add Cloudflare Workers for signed URL auth |
| Notifications | None | Add SNS/webhook on transcode complete |
| Error visibility | Logged to journalctl only | Ship logs to CloudWatch or Loki |
| Scaling | Single server | Add a queue (SQS/RabbitMQ) + multiple workers |
| Auth | SSH password or key | Use SSH certificates or SSM Session Manager |
| Resolutions | Hardcoded 360/480/720p | Make resolution list a variable |
| Input formats | `.mp4 .mov .mkv .avi .webm .m4v` | Configurable via variable |
