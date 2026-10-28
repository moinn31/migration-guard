import shutil

import pytest

from backend.migration_engine import run_openrewrite_docker


@pytest.mark.integration
def test_openrewrite_docker_sandbox_available():
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    pytest.skip("OpenRewrite integration requires the configured Maven mirror and is environment-specific.")
