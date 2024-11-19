import pydantic_settings

from .log import get_logger

logger = get_logger()

byte_sizes = {
    'kb': 1_000,
    'mb': 1_000**2,
    'gb': 1_000**3,
    'kib': 1_024,
    'mib': 1_024**2,
    'gib': 1_024**3,
    'b': 1,
    'k': 1_000,
    'm': 1_000**2,
    'g': 1_000**3,
    'ki': 1024,
    'mi': 1_024**2,
    'gi': 1_024**3,
}


def format_bytes(num: int) -> str:
    """Format bytes as a human readable string"""
    return next(
        (
            f'{num / value:.2f} {prefix}B'
            for prefix, value in (
                ('Gi', 2**30),
                ('Mi', 2**20),
                ('ki', 2**10),
            )
            if num >= value * 0.9
        ),
        f'{num} B',
    )


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        env_file=('.env', '.env.prod', '.env.local'), extra='ignore'
    )
    ZENODO_URL: str | None
    ZENODO_ACCESS_TOKEN: str | None
    ZENODO_MAX_FILE_SIZE: int = 15 * 1024 * 1024 * 1024
    JANEWAY_URL: str | None


def get_settings() -> Settings:
    logger.info('Loading settings from environment variables')
    return Settings()
