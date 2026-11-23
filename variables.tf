variable "server_ip" {
  description = "Public IP of the Utho instance."
  type        = string
}

variable "ssh_user" {
  description = "User Terraform logs in as (root, ubuntu or deploy). Needs sudo."
  type        = string
  default     = "root"
}

variable "ssh_password" {
  description = "Password of ssh_user (root password). Leave empty to use a key instead."
  type        = string
  sensitive   = true
  default     = ""
}

variable "ssh_private_key_path" {
  description = "Private key for the instance (no passphrase)."
  type        = string
  default     = "~/.ssh/id_ed25519"
}

variable "app_user" {
  description = "Linux user that runs the worker. Created if missing."
  type        = string
  default     = "deploy"
}

variable "s3_endpoint" {
  description = "Utho object storage endpoint URL."
  type        = string
}

variable "s3_region" {
  description = "Storage region name from the Utho dashboard."
  type        = string
  default     = "us-east-1"
}

variable "s3_access_key" {
  type      = string
  sensitive = true
}

variable "s3_secret_key" {
  type      = string
  sensitive = true
}

variable "raw_bucket" {
  type    = string
  default = "raw"
}

variable "processed_bucket" {
  type    = string
  default = "processed"
}

variable "poll_seconds" {
  type    = number
  default = 10
}

variable "grafana_password" {
  description = "Grafana admin password. Access Grafana at http://<server_ip>:3000 with user 'admin'."
  type        = string
  sensitive   = true
  default     = "admin"
}


# ── CDN (Cloudflare) ──────────────────────────────────────────────────────────

variable "cdn_enabled" {
  description = "Set to true to create a Cloudflare CDN in front of the processed bucket."
  type        = bool
  default     = false
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with Zone:Edit permissions. Can also be set via CLOUDFLARE_API_TOKEN env var."
  type        = string
  sensitive   = true
  default     = ""
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for the domain. Found in Cloudflare dashboard → Overview → right panel."
  type        = string
  default     = ""
}

variable "cdn_subdomain" {
  description = "Subdomain label for the CDN. E.g. 'videos' creates videos.apkaai.com."
  type        = string
  default     = "videos"
}

# ── Zoom Webhook ──────────────────────────────────────────────────────────────

variable "zoom_webhook_secret" {
  description = "Secret token from Zoom Marketplace app → Feature → Webhook. Used to verify incoming webhook signatures."
  type        = string
  sensitive   = true
  default     = ""
}

variable "zoom_webhook_port" {
  description = "Port the Zoom webhook server listens on. Must be open in firewall."
  type        = number
  default     = 8080
}
