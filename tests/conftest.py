import pytest

from coolroof.config import load_config


@pytest.fixture
def cfg():
    return load_config()
