# Deploys the worker + transcoder to the EXISTING Utho server and buckets.
# Code is in app/, server-side templates are in templates/.
# CDN is not here: the client sets it up on the "processed" bucket.

locals {
  # Files rendered from templates/ (variables filled in)
  env_file = templatefile("${path.module}/templates/video-worker.env.tftpl", {
    s3_endpoint      = var.s3_endpoint
    s3_region        = var.s3_region
    s3_access_key    = var.s3_access_key
    s3_secret_key    = var.s3_secret_key
    raw_bucket       = var.raw_bucket
    processed_bucket = var.processed_bucket
    poll_seconds     = var.poll_seconds
    cdn_base_url     = local.cdn_base_url
  })

  zoom_webhook_env = templatefile("${path.module}/templates/zoom-webhook.env.tftpl", {
    zoom_webhook_secret = var.zoom_webhook_secret
    zoom_webhook_port   = var.zoom_webhook_port
    s3_endpoint         = var.s3_endpoint
    s3_region           = var.s3_region
    s3_access_key       = var.s3_access_key
    s3_secret_key       = var.s3_secret_key
    raw_bucket          = var.raw_bucket
  })

  zoom_webhook_service = templatefile("${path.module}/templates/zoom-webhook.service.tftpl", {
    app_user = var.app_user
  })

  service_unit = templatefile("${path.module}/templates/video-worker.service.tftpl", {
    app_user = var.app_user
  })

  install_sh = templatefile("${path.module}/templates/install.sh.tftpl", {
    app_user         = var.app_user
    grafana_password = var.grafana_password
    zoom_webhook_port = var.zoom_webhook_port
  })

  prometheus_yml       = file("${path.module}/templates/prometheus.yml.tftpl")
  grafana_datasources  = file("${path.module}/templates/grafana-datasources.yml.tftpl")
  promtail_yml         = file("${path.module}/templates/promtail.yml.tftpl")
}

resource "terraform_data" "video_worker" {
  # Re-deploys when any code, setting, or the server IP changes.
  triggers_replace = [
    filesha1("${path.module}/app/transcoder.py"),
    filesha1("${path.module}/app/worker.py"),
    filesha1("${path.module}/app/storage_tool.py"),
    sha1(local.service_unit),
    sha1(local.install_sh),
    nonsensitive(sha1(local.env_file)),
    sha1(local.prometheus_yml),
    sha1(local.grafana_datasources),
    sha1(local.promtail_yml),
    var.server_ip,
    local.cdn_base_url,   # re-deploy when CDN is toggled on/off or URL changes
    nonsensitive(sha1(local.zoom_webhook_env)),
    sha1(local.zoom_webhook_service),
    filesha1("${path.module}/app/zoom_webhook.py"),
  ]

  connection {
    type        = "ssh"
    host        = var.server_ip
    user        = var.ssh_user
    password    = var.ssh_password != "" ? var.ssh_password : null
    private_key = try(file(pathexpand(var.ssh_private_key_path)), null)
    timeout     = "10m"
  }

  # 1. FIRST block: only create the folder
  provisioner "remote-exec" {
    inline = [
      "sudo rm -rf /tmp/vp",
      "mkdir -p /tmp/vp",
    ]
  }

  # 2. Upload files (app code, env, service, install.sh, monitoring configs)
  provisioner "file" {
    source      = "${path.module}/app/transcoder.py"
    destination = "/tmp/vp/transcoder.py"
  }

  provisioner "file" {
    source      = "${path.module}/app/worker.py"
    destination = "/tmp/vp/worker.py"
  }

  provisioner "file" {
    source      = "${path.module}/app/storage_tool.py"
    destination = "/tmp/vp/storage_tool.py"
  }

  provisioner "file" {
    source      = "${path.module}/app/zoom_webhook.py"
    destination = "/tmp/vp/zoom_webhook.py"
  }

  provisioner "file" {
    content     = local.zoom_webhook_env
    destination = "/tmp/vp/zoom-webhook.env"
  }

  provisioner "file" {
    content     = local.zoom_webhook_service
    destination = "/tmp/vp/zoom-webhook.service"
  }

  provisioner "file" {
    content     = local.env_file
    destination = "/tmp/vp/video-worker.env"
  }

  provisioner "file" {
    content     = local.service_unit
    destination = "/tmp/vp/video-worker.service"
  }

  provisioner "file" {
    content     = local.install_sh
    destination = "/tmp/vp/install.sh"
  }

  provisioner "file" {
    content     = local.prometheus_yml
    destination = "/tmp/vp/prometheus.yml"
  }

  provisioner "file" {
    content     = local.grafana_datasources
    destination = "/tmp/vp/grafana-datasources.yml"
  }

  provisioner "file" {
    content     = local.promtail_yml
    destination = "/tmp/vp/promtail.yml"
  }

  # 3. LAST block: install, test, clean up
  provisioner "remote-exec" {
    inline = [
      "set -e",
      "sudo bash /tmp/vp/install.sh",
      "sudo vp-storage check",
      "systemctl is-active video-worker",
      "systemctl is-active zoom-webhook",
      "sudo rm -rf /tmp/vp",
    ]
  }
}
