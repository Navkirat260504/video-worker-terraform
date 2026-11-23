output "grafana_url" {
  value = "http://${var.server_ip}:3000  |  user: admin  |  password: <your grafana_password>"
}

output "ssh_command" {
  value = "ssh ${var.ssh_user}@${var.server_ip}"
}

output "watch_logs" {
  value = "ssh ${var.ssh_user}@${var.server_ip} 'sudo journalctl -u video-worker -f'"
}

output "test_upload" {
  value = "ssh ${var.ssh_user}@${var.server_ip} 'sudo vp-storage upload ~/demo.mp4 && sudo vp-storage list'"
}

output "processed_bucket_url" {
  description = "Public base URL for the processed bucket. Files accessible as <url>/<video-id>/<resolution>.mp4"
  value       = "https://bucket-${var.processed_bucket}.${replace(var.s3_endpoint, "https://", "")}"
}

output "cdn_url" {
  description = "CDN base URL (videos.apkaai.com). Empty when cdn_enabled = false."
  value       = var.cdn_enabled ? "https://${var.cdn_subdomain}.${data.cloudflare_zone.zone[0].name}" : "(CDN disabled — set cdn_enabled = true to activate)"
}

output "zoom_webhook_url" {
  description = "Paste this URL into Zoom Marketplace app → Feature → Webhook → Event notification endpoint URL."
  value       = "https://webhook.apkaai.com/webhook"
}
