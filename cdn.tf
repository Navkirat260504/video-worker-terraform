# CDN layer: Cloudflare sits in front of the Utho processed bucket.
#
# What this creates (when cdn_enabled = true):
#   1. A CNAME DNS record  cdn_subdomain.your-zone  →  processed-bucket.s3-endpoint
#   2. A Cloudflare cache rule that caches all /video/* objects at the edge

locals {
  cdn_enabled = var.cdn_enabled

  s3_origin_host = "bucket-${var.processed_bucket}.${replace(var.s3_endpoint, "https://", "")}"
  cdn_base_url   = local.cdn_enabled ? "https://${var.cdn_subdomain}.${data.cloudflare_zone.zone[0].name}" : ""
}

# ── Cloudflare provider ───────────────────────────────────────────────────────
provider "cloudflare" {
  api_token = var.cloudflare_api_token != "" ? var.cloudflare_api_token : null
}

# ── Look up the zone ──────────────────────────────────────────────────────────
data "cloudflare_zone" "zone" {
  count   = local.cdn_enabled ? 1 : 0
  zone_id = var.cloudflare_zone_id
}

# ── 1. CNAME: videos.apkaai.com → bucket-processed.innoida.utho.io ───────────
resource "cloudflare_record" "cdn_cname" {
  count   = local.cdn_enabled ? 1 : 0
  zone_id = var.cloudflare_zone_id
  name    = var.cdn_subdomain
  type    = "CNAME"
  content = local.s3_origin_host
  proxied = true
  ttl     = 1
  comment = "Video CDN — managed by Terraform"
}

# ── 2. Cache rule ─────────────────────────────────────────────────────────────
resource "cloudflare_ruleset" "cdn_cache" {
  count       = local.cdn_enabled ? 1 : 0
  zone_id     = var.cloudflare_zone_id
  name        = "Video CDN cache rules"
  description = "Cache video renditions and manifests from Utho S3"
  kind        = "zone"
  phase       = "http_request_cache_settings"

  rules {
    description = "Cache video files for 1 year"
    expression  = "(http.host eq \"${var.cdn_subdomain}.${data.cloudflare_zone.zone[0].name}\" and ends_with(http.request.uri.path, \".mp4\"))"
    action      = "set_cache_settings"
    action_parameters {
      cache = true
      edge_ttl {
        mode    = "override_origin"
        default = 31536000
      }
      browser_ttl {
        mode    = "override_origin"
        default = 31536000
      }
    }
    enabled = true
  }

  rules {
    description = "Cache manifests for 60 seconds"
    expression  = "(http.host eq \"${var.cdn_subdomain}.${data.cloudflare_zone.zone[0].name}\" and ends_with(http.request.uri.path, \"manifest.json\"))"
    action      = "set_cache_settings"
    action_parameters {
      cache = true
      edge_ttl {
        mode    = "override_origin"
        default = 60
      }
      browser_ttl {
        mode    = "override_origin"
        default = 60
      }
    }
    enabled = true
  }
}
