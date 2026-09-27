"""Integration tests against the real Redis + PostgreSQL started by `docker compose up`.

Set TEST_DATABASE_URL and TEST_REDIS_URL to run them (see docs/setup.md). They are skipped
otherwise so the unit suite still runs on a machine without Docker.
"""
import dataclasses
import os

import pytest

from app.config import load_settings
from app.dependencies import build_dependencies

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
REDIS_URL = os.getenv("TEST_REDIS_URL")
SEED_COUNT = 50

# Skipped (not failed) without a running stack: these need real containers, see module docstring.
pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and REDIS_URL), reason="TEST_DATABASE_URL / TEST_REDIS_URL not set"
)


@pytest.fixture
def deps():
    settings = dataclasses.replace(
        load_settings(),
        database_url=DATABASE_URL,
        redis_url=REDIS_URL,
        slow_query_ms=0,
        seed_product_count=SEED_COUNT,
    )
    dependencies = build_dependencies(settings)
    yield dependencies
    dependencies.close()


def test_seeded_product_is_readable_from_postgres(deps):
    assert deps.repo.get_product(1)["name"] == "Product 001"


def test_list_is_ordered_by_id(deps):
    assert [p["id"] for p in deps.repo.list_products(3)] == [1, 2, 3]


def test_services_answer_health_checks(deps):
    assert (deps.repo.ping(), deps.cache.ping()) == (True, True)


def test_real_redis_reports_a_memory_limit(deps):
    assert deps.cache.memory_stats().max_bytes > 0
