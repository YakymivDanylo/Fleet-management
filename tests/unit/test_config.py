import importlib

import pytest
from pydantic import ValidationError

from fleet_management import config
from fleet_management.config import Settings

SANDBOX_DB = "postgresql+asyncpg://u:p@db:5432/fleet_sandbox"
TEST_DB = "postgresql+asyncpg://u:p@db:5432/fleet_management_test"
PRODUCTION_DB = "postgresql+asyncpg://u:p@db:5432/fleet_production"
LONG_SECRET = "s" * 40


def build(**overrides) -> Settings:
    # _env_file=None: unit tests must not depend on a developer's local .env.* files.
    return Settings(_env_file=None, **overrides)


def test_sandbox_is_the_default_environment():
    settings = build(database_url=SANDBOX_DB)
    assert settings.app_env == "sandbox"
    assert not settings.is_production


def test_sandbox_allows_debug_and_test_database():
    assert build(database_url=SANDBOX_DB, debug=True).debug is True
    assert build(database_url=TEST_DB).app_env == "sandbox"


def test_production_accepts_production_database():
    settings = build(app_env="production", database_url=PRODUCTION_DB, jwt_secret_key=LONG_SECRET)
    assert settings.is_production
    assert settings.debug is False


def test_production_refuses_debug():
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        build(
            app_env="production",
            database_url=PRODUCTION_DB,
            jwt_secret_key=LONG_SECRET,
            debug=True,
        )


@pytest.mark.parametrize("secret", [None, "", "too-short"])
def test_production_requires_a_strong_jwt_secret(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        build(app_env="production", database_url=PRODUCTION_DB, jwt_secret_key=secret)


@pytest.mark.parametrize("database_url", [SANDBOX_DB, TEST_DB])
def test_production_refuses_sandbox_or_test_database(database_url):
    with pytest.raises(ValidationError, match="requires a database name ending with"):
        build(app_env="production", database_url=database_url, jwt_secret_key=LONG_SECRET)


def test_sandbox_refuses_production_database():
    with pytest.raises(ValidationError, match="requires a database name ending with"):
        build(database_url=PRODUCTION_DB)


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        build()


def test_unknown_environment_is_rejected():
    with pytest.raises(ValidationError):
        build(app_env="staging", database_url=SANDBOX_DB)


def test_code_defaults_contain_no_credentials(monkeypatch):
    for name in ("RABBITMQ_URL", "REDIS_URL", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = build(database_url=SANDBOX_DB)
    assert "@" not in settings.rabbitmq_url
    assert "@" not in settings.redis_url
    assert settings.jwt_secret_key is None


def test_env_file_is_chosen_by_app_env(tmp_path, monkeypatch):
    (tmp_path / ".env.production").write_text(
        f"DEBUG=false\nDATABASE_URL={PRODUCTION_DB}\nJWT_SECRET_KEY={LONG_SECRET}\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.sandbox").write_text(
        f"DEBUG=true\nDATABASE_URL={SANDBOX_DB}\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    for name in ("DATABASE_URL", "DEBUG", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    try:
        monkeypatch.setenv("APP_ENV", "production")
        production = importlib.reload(config).Settings()
        monkeypatch.setenv("APP_ENV", "sandbox")
        sandbox = importlib.reload(config).Settings()
    finally:
        # Restore the module state the rest of the suite relies on.
        monkeypatch.undo()
        importlib.reload(config)

    assert production.is_production and production.debug is False
    assert sandbox.app_env == "sandbox" and sandbox.debug is True


def test_real_environment_variables_override_the_env_file(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", SANDBOX_DB)
    monkeypatch.setenv("DEBUG", "true")
    assert Settings(_env_file=None).debug is True
