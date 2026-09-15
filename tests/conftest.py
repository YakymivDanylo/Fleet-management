import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fleet_user:fleet_password@localhost:5432/fleet_management_test",
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
