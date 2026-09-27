from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.handlers import SkillHandler
from app.llm import LlmService
from app.protocol import parse_request
from app.storage import Storage


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
    llm: LlmService | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    storage = storage or Storage(settings.db_path)
    llm = llm or LlmService(settings, storage)
    handler = SkillHandler(settings, storage, llm)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await llm.aclose()
        storage.close()

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.storage = storage
    app.state.llm = llm

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/alice")
    async def alice(request: Request) -> JSONResponse:
        payload = await request.json()
        alice_request = parse_request(payload)
        if settings.skill_id and alice_request.skill_id != settings.skill_id:
            return JSONResponse(status_code=403, content={"error": "unknown skill"})
        response = await handler.handle(alice_request)
        return JSONResponse(content=response)

    return app
