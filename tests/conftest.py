import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fleet_user:fleet_password@localhost:5432/fleet_management_test",
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")

# Tests always run as sandbox, whatever the developer's shell has exported; the "_test"
# database suffix is accepted in sandbox only (see fleet_management.config).
os.environ["APP_ENV"] = "sandbox"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL
# Test-only key; real deployments must provide their own secret.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use-0123456789")
