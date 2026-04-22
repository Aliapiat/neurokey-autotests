import pytest

from config.environments import ENVIRONMENTS
from config.settings import settings


def pytest_addoption(parser):
    parser.addoption(
        "--env",
        action="store",
        default="dev",
        choices=list(ENVIRONMENTS.keys()),
        help="Target environment (dev/prod)",
    )


@pytest.fixture(scope="session", autouse=True)
def set_environment(request):
    env = request.config.getoption("--env")
    settings.BASE_URL = ENVIRONMENTS[env]
    settings.CURRENT_ENV = env
    print(f"\n🔗 Target: {env} → {settings.BASE_URL}")
    yield
