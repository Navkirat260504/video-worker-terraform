# CareerLauncher Video Pipeline — Project Documentation

## Overview

A fully automated video transcoding pipeline deployed on Utho Cloud. Zoom cloud recordings are automatically captured via webhook, transcoded into multiple resolutions, and served globally via Cloudflare CDN — with zero manual intervention.

---

## Full Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ZOOM CLOUD                                      │
│   Host ends meeting → Zoom processes recording → recording.completed    │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ POST webhook
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ngrok tunnel (temporary)                           │
│              https://drift-yoga-rule.ngrok-free.dev/webhook             │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Utho Cloud Server (103.209.147.15)                │
│                                                                         │
│  ┌─────────────────┐    ┌──────────────────────────────────────────┐   │
│  │  nginx (:80)    │───▶│  zoom_webhook.py (Flask :8080)           │   │
│  │  reverse proxy  │    │  - Validates HMAC signature              │   │
│  └─────────────────┘    │  - Downloads MP4 from Zoom               │   │
│                         │  - Uploads to careerlauncher-raw         │   │
│                         └──────────────────┬─────────────────────--┘   │
│                                            │ upload                     │
│  ┌──────────────────────────────────────┐  │                            │
│  │  worker.py (systemd, polls 10s)      │◀─┘ detects new file          │
│  │  - Downloads from raw bucket        │                               │
│  │  - Calls transcoder.py (ffmpeg)     │                               │
│  │  - Uploads 360p/480p/720p/1080p     │                               │
│  │  - Writes manifest.json             │                               │
│  └──────────────────────────────────────┘                              │
│                                                                         │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────────┐ │
│  │  Redis       │  │  Prometheus   │  │  Grafana (:3000)             │ │
│  │  (dedup lock)│  │  + Loki       │  │  Dashboards + Logs           │ │
│  └──────────────┘  └───────────────┘  └──────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ upload renditions
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Utho S3 — careerlauncher-processed                   │
│                                                                         │
│   <video-id>/360p.mp4        <video-id>/480p.mp4                        │
│   <video-id>/720p.mp4        <video-id>/1080p.mp4                       │
│   <video-id>/manifest.json                                              │
│                                                                         │
│   Origin URL: https://bucket-careerlauncher-processed.innoida.utho.io  │
└─────────────────────────────────────────────────────────────────────────┘
                               │ origin pull
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Cloudflare CDN                                     │
│                   https://videos.apkaai.com                             │
│                                                                         │
│   .mp4 files  → cached 1 year (immutable)                              │
│   manifest    → cached 60 seconds                                       │
└─────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                          End Users / LMS
```

---

## Data Flow

```
1. Zoom meeting ends
2. Zoom sends POST to webhook URL (recording.completed)
3. zoom_webhook.py validates HMAC signature
4. Downloads each MP4 from Zoom
5. Uploads to careerlauncher-raw/<topic>_<id>_<date>.mp4
6. worker.py polls raw bucket every 10s — detects new file
7. Redis lock acquired (prevents duplicate processing)
8. Video downloaded to /tmp
9. ffmpeg transcodes to 360p → 480p → 720p → 1080p
10. Each rendition uploaded to careerlauncher-processed
11. manifest.json written last (signals completion)
12. Client fetches manifest → streams via CDN
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Infrastructure | Terraform >= 1.4.0 |
| Cloud Provider | Utho Cloud |
| Object Storage | Utho S3-compatible (innoida zone) |
| Webhook Server | Python + Flask |
| Transcoding | Python + ffmpeg |
| Deduplication | Redis (localhost only) |
| Process Manager | systemd |
| Tunnel (temp) | ngrok |
| CDN | Cloudflare (videos.apkaai.com) |
| Monitoring | Prometheus + Grafana + Loki + Promtail |

---

## Project Structure

```
video-worker-terraform/
├── main.tf                          # Core Terraform — SSH deploy
├── variables.tf                     # All input variables
├── outputs.tf                       # URLs and commands after apply
├── versions.tf                      # Terraform + provider versions
├── cdn.tf                           # Cloudflare CDN resources
├── terraform.tfvars                 # Variable values (gitignored)
│
├── app/
│   ├── worker.py                    # Polling loop + S3 + Redis
│   ├── transcoder.py                # ffmpeg wrapper (360p–1080p)
│   ├── storage_tool.py              # CLI: vp-storage check|upload|list
│   └── zoom_webhook.py              # Flask webhook server
│
└── templates/
    ├── install.sh.tftpl             # Server bootstrap script
    ├── video-worker.env.tftpl       # Worker env file
    ├── video-worker.service.tftpl   # Worker systemd unit
    ├── zoom-webhook.env.tftpl       # Webhook env file
    ├── zoom-webhook.service.tftpl   # Webhook systemd unit
    ├── prometheus.yml.tftpl         # Prometheus scrape config
    ├── grafana-datasources.yml.tftpl# Grafana datasource config
    └── promtail.yml.tftpl           # Promtail log shipping config
```

---

## Infrastructure

| Server | IP | Provider |
|---|---|---|
| CareerLauncher1 | 103.209.147.15 | Utho Cloud |

| Bucket | Purpose | Access |
|---|---|---|
| `careerlauncher-raw` | Incoming raw videos | Private |
| `careerlauncher-processed` | Transcoded renditions | Public Read |

| Domain | Purpose |
|---|---|
| `videos.apkaai.com` | CDN for processed videos |
| `webhook.apkaai.com` | HTTPS proxy for Zoom webhook (nginx) |

---

## Input Variables

| Variable | Default | Description |
|---|---|---|
| `server_ip` | — | Utho server public IP |
| `ssh_user` | `root` | SSH login user |
| `ssh_password` | — | SSH password |
| `app_user` | `deploy` | Linux user running the worker |
| `s3_endpoint` | — | Utho S3 endpoint URL |
| `s3_region` | `innoida` | Storage region |
| `s3_access_key` | — | S3 access key |
| `s3_secret_key` | — | S3 secret key |
| `raw_bucket` | `careerlauncher-raw` | Raw video bucket |
| `processed_bucket` | `careerlauncher-processed` | Processed video bucket |
| `poll_seconds` | `10` | Worker poll interval |
| `grafana_password` | — | Grafana admin password |
| `cdn_enabled` | `true` | Enable Cloudflare CDN |
| `cloudflare_api_token` | — | Cloudflare API token |
| `cloudflare_zone_id` | — | Cloudflare Zone ID (apkaai.com) |
| `cdn_subdomain` | `videos` | CDN subdomain |
| `zoom_webhook_secret` | — | Zoom webhook secret token |
| `zoom_webhook_port` | `8080` | Webhook server port |

---

## Outputs

| Output | Value |
|---|---|
| `ssh_command` | `ssh root@103.209.147.15` |
| `watch_logs` | journalctl command for worker logs |
| `test_upload` | vp-storage upload command |
| `grafana_url` | `http://103.209.147.15:3000` |
| `processed_bucket_url` | Direct S3 URL for processed bucket |
| `cdn_url` | `https://videos.apkaai.com` |
| `zoom_webhook_url` | `https://webhook.apkaai.com/webhook` |

---

## Zoom Webhook Integration

### Setup

| Setting | Value |
|---|---|
| App Name | recording.complete |
| App Type | Webhook Only |
| Secret Token | stored in `zoom_webhook_secret` variable |
| Endpoint URL | `https://drift-yoga-rule.ngrok-free.dev/webhook` (ngrok, temporary) |
| Event | Recording → All Recordings have completed |
| Status | ✅ Activated |

### Important — ngrok URL changes on restart

The current ngrok URL is temporary. When the server restarts, run:
```bash
nohup ngrok http 8080 > /tmp/ngrok.log 2>&1 &
sleep 5
curl -s http://localhost:4040/api/tunnels | python3 -c \
  "import sys,json; t=json.load(sys.stdin)['tunnels']; print(t[0]['public_url'])"
```
Then update the URL in Zoom Marketplace → Feature → Event Subscriptions.

**Permanent fix:** `webhook.apkaai.com` is configured with nginx — once Cloudflare resolves the SSL issue, switch to `https://webhook.apkaai.com/webhook`.

### Zoom Recording Settings Required

- **Require passcode to access shared cloud recordings** → OFF
- **Record to Cloud** must be selected when recording

---

## Monitoring

| Service | Port | URL |
|---|---|---|
| Grafana | 3000 | `http://103.209.147.15:3000` (admin / Admin@1234) |
| Prometheus | 9090 | localhost only |
| Loki | 3100 | localhost only |
| Node Exporter | 9100 | localhost only |
| Redis Exporter | 9121 | localhost only |

### Grafana Dashboards

| Dashboard | ID | Datasource |
|---|---|---|
| Node Exporter Full | 1860 | Prometheus |
| Redis | 763 | Prometheus |
| Video Worker Logs | Explore | Loki → `{job="video-worker"}` |
| Zoom Webhook Logs | Explore | Loki → `{job="zoom-webhook"}` |

---

## Operational Runbook

| Task | Command |
|---|---|
| Watch worker logs | `journalctl -u video-worker -f` |
| Watch webhook logs | `journalctl -u zoom-webhook -f` |
| Watch both | `journalctl -u video-worker -u zoom-webhook -f` |
| Restart worker | `systemctl restart video-worker` |
| Restart webhook | `systemctl restart zoom-webhook` |
| List raw bucket | `aws --endpoint-url https://innoida.utho.io --region innoida s3 ls s3://careerlauncher-raw` |
| List processed bucket | `aws --endpoint-url https://innoida.utho.io --region innoida s3 ls s3://careerlauncher-processed --recursive` |
| Check storage | `vp-storage check` |
| Restart monitoring | `systemctl restart prometheus node-exporter redis-exporter loki promtail grafana-server` |

---

## CDN URLs

After transcoding completes, videos are available at:

```
https://videos.apkaai.com/<video-id>/360p.mp4
https://videos.apkaai.com/<video-id>/480p.mp4
https://videos.apkaai.com/<video-id>/720p.mp4
https://videos.apkaai.com/<video-id>/1080p.mp4
https://videos.apkaai.com/<video-id>/manifest.json
```

Example manifest response:
```json
{
  "id": "rahtest2_89463198876_2026-11-19T05_52_12_0",
  "source": "rahtest2_89463198876_2026-11-19T05_52_12_0.mp4",
  "cdn": true,
  "files": {
    "360p": "https://videos.apkaai.com/rahtest2_.../360p.mp4",
    "480p": "https://videos.apkaai.com/rahtest2_.../480p.mp4",
    "720p": "https://videos.apkaai.com/rahtest2_.../720p.mp4",
    "1080p": "https://videos.apkaai.com/rahtest2_.../1080p.mp4"
  }
}
```

---

## Security Notes

- S3 credentials are `sensitive = true` in Terraform
- `/etc/video-worker.env` and `/etc/zoom-webhook.env` are mode `640` (root:app_user)
- Redis bound to `127.0.0.1` only
- Worker runs as non-root `deploy` user
- Zoom webhook signature verified via HMAC-SHA256 on every request
- Raw bucket is private — only accessible via server credentials
- Processed bucket is public-read for CDN access

---

## Known Issues & Next Steps

| Issue | Status | Fix |
|---|---|---|
| ngrok URL temporary | Open | Switch to `webhook.apkaai.com` permanently once Cloudflare SSL resolved |
| Zoom download requires auth | Resolved | Disabled recording passcode in Zoom settings |
| Bucket object-level ACL | N/A | Utho doesn't support object ACL API — use bucket-level public read |
| CDN direct URL | Open | Verify `https://videos.apkaai.com/<id>/360p.mp4` works after bucket public read confirmed |
