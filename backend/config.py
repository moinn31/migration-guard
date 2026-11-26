from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./migrationguard.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False
    jwt_secret: str = "local-development-only-change-me"
    jwt_expire_minutes: int = 60
    app_env: str = "development"
    migrationguard_enable_execution: bool = False
    maven_mirror: str | None = None
    workspace_root: str = "./migrationguard-workspaces"
    openrewrite_plugin_version: str = "6.17.0"
    openrewrite_recipe_version: str = "3.17.0"
    openrewrite_recipes: str = "org.openrewrite.java.migrate.UpgradeToJava17"
    migration_dry_run: bool = False
    llm_provider: str | None = None
    llm_model: str = "default"
    llm_api_key: str | None = None
    github_token: str | None = None
    report_share_secret: str = "local-development-report-secret"
    llm_rate_limit_per_minute: int = 10
    
    # Clerk Authentication
    clerk_secret_key: str | None = None
    clerk_issuer: str | None = None
    next_public_clerk_publishable_key: str | None = None
    clerk_audience: str | None = None
    clerk_authorized_parties: list[str] = []
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"]
    terminal_timeout_seconds: int = 300
    agent_max_retries: int = 3
    camber_api_key: str | None = None
    camber_mcp_access_token: str | None = None
    camber_fixer_agent: str | None = None
    camber_chat_agent: str | None = None
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    workspace_execution_enabled: bool = False
    backend_public_url: str | None = None
    # Each project gets its own isolated Azure workspace URL and bearer token.
    azure_workspaces: dict[str, dict[str, str]] = {}

    # Azure Container Apps Jobs
    azure_enabled: bool = False
    azure_subscription_id: str = ""
    azure_resource_group: str = "rg-migration-platform"
    azure_containerapps_environment: str = "env-migration-standard"
    azure_containerapps_job_name: str = "migration-worker"
    azure_location: str = "centralindia"

    model_config = SettingsConfigDict(env_file=(".env", ".env.development.local"), extra="ignore")

    @model_validator(mode="after")
    def validate_production_secret(self):
        if self.terminal_timeout_seconds <= 0 or not 1 <= self.agent_max_retries <= 5:
            raise ValueError('Terminal timeout must be positive and agent retries must be between 1 and 5')
        urls = [item.get('url', '').rstrip('/') for item in self.azure_workspaces.values()]
        if len(urls) != len(set(urls)):
            raise ValueError('Each project must have a separate Azure workspace URL')
        if self.app_env.lower() in {"production", "prod"} and (
            len(self.jwt_secret.encode("utf-8")) < 32
            or self.jwt_secret.startswith(("change-me", "local-development", "replace-"))
        ):
            raise ValueError("JWT_SECRET must be a unique random value of at least 32 bytes in production")
        return self


settings = Settings()
