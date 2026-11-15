"""The SPA fallback must serve only files inside the frontend build directory."""

import asyncio

import httpx

from api import risk_api


def _get(paths):
    async def run():
        transport = httpx.ASGITransport(app=risk_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return [await client.get(path) for path in paths]

    return asyncio.run(run())


def test_spa_fallback_serves_only_files_inside_the_frontend_directory(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend_dist"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text("<html>index</html>", encoding="utf-8")
    (frontend / "assets" / "app.js").write_text("console.log('inside')", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("OUTSIDE-FILE", encoding="utf-8")
    monkeypatch.setattr(risk_api, "FRONTEND_DIST", frontend)

    inside, index_for_unknown = _get(["/assets/app.js", "/some/client/route"])
    assert inside.status_code == 200 and "inside" in inside.text
    assert index_for_unknown.status_code == 200 and "index" in index_for_unknown.text

    escapes = [
        "/%2e%2e/outside.txt",
        "/..%2foutside.txt",
        "/%2e%2e%2foutside.txt",
        "/assets/%2e%2e/%2e%2e/outside.txt",
        "/..%5coutside.txt",
    ]
    for response in _get(escapes):
        assert "OUTSIDE-FILE" not in response.text
