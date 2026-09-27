import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.cache import ProductCache
from app.dependencies import Dependencies
from app.main import create_app
from app.service import ProductService

SAMPLE_PRODUCTS = [
    {"id": 1, "name": "Product 001", "category": "garden", "price_cents": 536, "stock": 13},
    {"id": 2, "name": "Product 002", "category": "kitchen", "price_cents": 573, "stock": 26},
]


class FakeRepository:
    def __init__(self, products: list[dict]) -> None:
        self.products = {p["id"]: p for p in products}
        self.is_up = True
        self.query_count = 0

    def get_product(self, product_id: int) -> dict | None:
        self.query_count += 1
        return self.products.get(product_id)

    def list_products(self, limit: int) -> list[dict]:
        self.query_count += 1
        return list(self.products.values())[:limit]

    def ping(self) -> bool:
        return self.is_up


@pytest.fixture
def fake_repo() -> FakeRepository:
    return FakeRepository(SAMPLE_PRODUCTS)


@pytest.fixture
def fake_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def client(fake_repo, fake_redis):
    def factory(settings):
        cache = ProductCache(fake_redis, settings.cache_ttl_seconds)
        service = ProductService(cache, fake_repo)
        return Dependencies(cache=cache, repo=fake_repo, service=service, close=lambda: None)

    with TestClient(create_app(factory)) as test_client:
        yield test_client
