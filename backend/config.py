from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    anthropic_base_url: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    database_url: str

    # File storage — raw uploads are NEVER written to disk (in-memory only)
    output_dir: str = "data/outputs"    # charts/exports only

    # Session — raw data held in RAM only; evict after this many idle seconds
    session_ttl_seconds: int = 1800     # 30 minutes

    # App
    max_upload_size_mb: int = 100
    allowed_extensions: str = "csv,xlsx,json,parquet"

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip() for ext in self.allowed_extensions.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
