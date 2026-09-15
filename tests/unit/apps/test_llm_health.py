from httpx import ASGITransport, AsyncClient
from revops.infrastructure.llm.fake import FakeLLMGateway

from apps.api.main import create_app


async def test_llm_health_is_public_and_sanitized() -> None:
    app = create_app(llm_gateway=FakeLLMGateway())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/llm")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "secret-test-key" not in response.text
    assert "prompt" not in response.text
