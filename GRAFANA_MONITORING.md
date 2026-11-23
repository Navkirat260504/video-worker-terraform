# Grafana Monitoring Guide

## Access Grafana

| Field    | Value                          |
|----------|-------------------------------|
| URL      | http://103.209.147.15:3000    |
| Username | admin                         |
| Password | Admin@1234                    |

---

## What's Being Monitored

| Service         | Tool             | What it tracks                        |
|-----------------|------------------|---------------------------------------|
| Server (OS)     | Node Exporter    | CPU, RAM, Disk, Network               |
| Redis           | Redis Exporter   | Connected clients, memory, commands   |
| Worker logs     | Loki + Promtail  | Live video-worker transcoding logs    |
| All metrics     | Prometheus       | Scrapes all exporters every 15s       |

---

## Step 1 — Import Node Exporter Dashboard (CPU / RAM / Disk)

1. In Grafana sidebar → **Dashboards → Import**
2. Enter ID: `1860` → click **Load**
3. Select **Prometheus** as datasource
4. Click **Import**

You will see:
- CPU usage per core
- RAM used / available
- Disk read/write
- Network in/out

---

## Step 2 — Import Redis Dashboard

1. **Dashboards → Import**
2. Enter ID: `763` → click **Load**
3. Select **Prometheus** as datasource
4. Click **Import**

You will see:
- Connected clients
- Memory usage
- Commands per second
- Keyspace hits/misses (video lock stats)

---

## Step 3 — View Video Worker Logs (Loki)

1. Click **Explore** (compass icon in left sidebar)
2. Select **Loki** from the top dropdown
3. Enter this query:
```
{job="video-worker"}
```
4. Click **Run query**

You will see live logs like:
```
Worker watching bucket 'careerlauncher-raw' every 10s
Processing demo.mp4
  360p done
  480p done
  720p done
  1080p done
Finished demo
```

---

## Step 4 — Verify Prometheus Targets Are Up

SSH into the server and run:
```bash
ssh root@103.209.147.15 "curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep health"
```

Expected output:
```
"health": "up",   <- node exporter
"health": "up",   <- redis exporter
```

If any show `"down"` run:
```bash
ssh root@103.209.147.15 "systemctl restart prometheus node-exporter redis-exporter"
```

---

## Useful SSH Commands

| Task                        | Command |
|-----------------------------|---------|
| Watch live worker logs      | `ssh root@103.209.147.15 'journalctl -u video-worker -f'` |
| Check Grafana status        | `ssh root@103.209.147.15 'systemctl status grafana-server'` |
| Check Prometheus status     | `ssh root@103.209.147.15 'systemctl status prometheus'` |
| Check Loki status           | `ssh root@103.209.147.15 'systemctl status loki'` |
| Restart all monitoring      | `ssh root@103.209.147.15 'systemctl restart prometheus node-exporter redis-exporter loki promtail grafana-server'` |
| Reset Grafana password      | `ssh root@103.209.147.15 'grafana cli --homepath /usr/share/grafana admin reset-admin-password Admin@1234'` |

---

## Monitoring Stack Architecture

```
┌─────────────────────────────────────────────────┐
│                 Utho Server                     │
│                                                 │
│  video-worker (systemd)                         │
│       │ logs                                    │
│       ▼                                         │
│  Promtail ──────────────▶ Loki (:3100)          │
│                                                 │
│  Node Exporter (:9100) ──┐                      │
│  Redis Exporter (:9121) ─┼──▶ Prometheus(:9090) │
│                          │         │            │
│                          │         ▼            │
│                          └───▶ Grafana (:3000)  │
└─────────────────────────────────────────────────┘
```

---

## Dashboard IDs Reference

| Dashboard          | Grafana ID | Datasource |
|--------------------|------------|------------|
| Node Exporter Full | 1860       | Prometheus |
| Redis              | 763        | Prometheus |
| Loki Logs          | Explore    | Loki       |
