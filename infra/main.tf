resource "render_background_worker" "participation_bot" {
  name           = "participation-bot"
  plan           = "starter"
  region         = "oregon"
  environment_id = var.dev_environment_id  # Assign to Dev environment

  start_command  = "python bots/participation_bot.py --data-dir /data"

  runtime_source = {
    native_runtime = {
      auto_deploy   = true
      branch        = "feature/dual-bots-sqlite"
      build_command = "pip install -r requirements.txt"
      repo_url      = var.github_repo
      runtime       = "python"
    }
  }

  env_vars = {
    DISCORD_TOKEN = {
      value = var.discord_token
    }
    TEXT_CHANNEL_ID = {
      value = var.text_channel_id
    }
  }

  disk = {
    mount_path = "/data"
    name       = "event-data-disk"
    size_gb    = 1
  }

  num_instances   = 1
}

resource "render_web_service" "dashboard_bot" {
  name               = "dashboard-bot"
  plan               = "starter"
  region             = "oregon"
  environment_id = var.dev_environment_id  # Assign to Dev environment

  start_command      = "/opt/render/project/src/.venv/bin/python -m gunicorn bots/dashboard_bot:app --bind 0.0.0.0:$PORT"

  runtime_source = {
    native_runtime = {
      auto_deploy   = false
      branch        = "feature/dual-bots-sqlite"
      build_command = "pip install -r requirements.txt"
      repo_url      = var.github_repo
      runtime       = "python"
    }
  }

  env_vars = {
    PORT = {
      value = "5000"
    }
  }

  disk = {
    mount_path = "/data"
    name       = "event-data-disk"
    size_gb    = 1
  }

  num_instances   = 1
}

output "participation_bot_url" {
  value = null  # Removed unsupported url, set to null or omit
}

output "dashboard_bot_url" {
  value = render_web_service.dashboard_bot.url
}