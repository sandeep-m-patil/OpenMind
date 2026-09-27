def test_health_reports_ok_when_dependencies_are_up(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok", "components": {"redis": "up", "postgres": "up"}}


def test_health_returns_503_when_postgres_is_down(client, fake_repo):
    fake_repo.is_up = False

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["data"]["components"]["postgres"] == "down"


def test_first_product_read_misses_cache_and_second_hits(client):
    first = client.get("/products/1")
    second = client.get("/products/1")

    assert (first.headers["x-cache"], second.headers["x-cache"]) == ("MISS", "HIT")


def test_cache_hit_does_not_query_the_database(client, fake_repo):
    client.get("/products/1")
    client.get("/products/1")

    assert fake_repo.query_count == 1


def test_product_body_uses_response_envelope(client):
    body = client.get("/products/2").json()

    assert (body["data"]["id"], body["meta"], body["error"]) == (2, {"cache": "MISS"}, None)


def test_unknown_product_returns_404_envelope(client):
    response = client.get("/products/999")

    assert response.status_code == 404
    assert response.json()["error"] == {"message": "product not found"}


def test_invalid_product_id_is_rejected(client):
    response = client.get("/products/0")

    assert response.status_code == 422


def test_list_products_respects_limit(client):
    body = client.get("/products", params={"limit": 1}).json()

    assert body["meta"]["count"] == 1


def test_list_limit_above_maximum_is_rejected(client):
    assert client.get("/products", params={"limit": 1000}).status_code == 422


def test_metrics_exposes_request_and_cache_metrics(client):
    client.get("/products/1")

    text = client.get("/metrics").text

    assert 'http_requests_total{method="GET",path="/products/{product_id}",status="200"}' in text
    assert "cache_misses_total" in text
