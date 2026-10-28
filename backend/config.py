from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./migrationguard.db"
    redis_url: str = "redis://localhost:6379/0"
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
    model_config = SettingsConfigDict(env_file=(".env", ".env.development.local"), extra="ignore")

    @model_validator(mode="after")
    def validate_production_secret(self):
        if self.app_env.lower() in {"production", "prod"} and (
            len(self.jwt_secret.encode("utf-8")) < 32
            or self.jwt_secret.startswith(("change-me", "local-development", "replace-"))
        ):
            raise ValueError("JWT_SECRET must be a unique random value of at least 32 bytes in production")
        return self


settings = Settings()
