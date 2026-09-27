"""Cache-aside product lookups: try Redis first, fall back to PostgreSQL, then fill the cache."""
from app.cache import ProductCache
from app.metrics import CACHE_HITS, CACHE_MISSES

CACHE_HIT = "HIT"
CACHE_MISS = "MISS"


class ProductService:
    def __init__(self, cache: ProductCache, repo) -> None:
        self._cache = cache
        self._repo = repo

    def get_product(self, product_id: int) -> tuple[dict | None, str]:
        return self._cached(f"product:{product_id}", lambda: self._repo.get_product(product_id))

    def list_products(self, limit: int) -> tuple[list[dict], str]:
        return self._cached(f"products:list:{limit}", lambda: self._repo.list_products(limit))

    def _cached(self, key: str, load):
        cached = self._cache.get_json(key)
        if cached is not None:
            CACHE_HITS.inc()
            return cached, CACHE_HIT
        CACHE_MISSES.inc()
        value = load()
        if value is not None:
            self._cache.set_json(key, value)
        return value, CACHE_MISS
