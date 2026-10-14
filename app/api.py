"""API for local checkout challenges and explicit maintainer solution reveal."""

import logging
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .agents.schemas import RepositoryInput
from .orchestration.langgraph_generation import LangGraphGenerationWorkflow
from .persistence import ChallengeStore

logger = logging.getLogger(__name__)


class GenerateRequest(RepositoryInput):
    use_cache: bool = True
    cache_only: bool = True


def create_app(*, store: ChallengeStore | None = None,
               workflow: LangGraphGenerationWorkflow | None = None) -> FastAPI:
    app = FastAPI(title="Accelerate — local repository challenges", version="0.2.0")
    origins = os.getenv("ACCELERATE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    app.add_middleware(CORSMiddleware,
        allow_origins=[item.strip() for item in origins.split(",") if item.strip()],
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    challenge_store = store or ChallengeStore()
    generation_workflow = workflow or LangGraphGenerationWorkflow()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/challenges")
    def list_challenges(limit: int = Query(default=20, ge=1, le=100)):
        return {"items": challenge_store.list_challenges(limit)}

    @app.post("/challenges/generate")
    def generate(request: GenerateRequest):
        if request.use_cache or request.cache_only:
            existing = challenge_store.find_challenge(request.repository)
            if existing:
                return {"challenge_id": existing["id"], "challenge": existing, "cached": True}
        if request.cache_only:
            raise HTTPException(status_code=409,
                detail="No saved challenge for this repository. Load cached demos, "
                       "or turn off cached-only mode to generate with an LLM.")
        try:
            result = generation_workflow.run(request, use_cache=request.use_cache)
            challenge_id = challenge_store.save_challenge(result.context.commit.repository,
                result.context.commit.commit_sha, result.problem, result.context.commit)
        except ValueError as error:
            logger.warning("Generation rejected: %s", error)
            raise HTTPException(status_code=422, detail="No grounded challenge could be generated from this repository.") from error
        except RuntimeError as error:
            logger.exception("Generation provider failure")
            raise HTTPException(status_code=502, detail="GitHub or the model provider could not complete generation. Check the API logs.") from error
        return {"challenge_id": challenge_id,
                "challenge": challenge_store.export_challenge(challenge_id), "cached": False}

    @app.get("/challenges/{challenge_id}")
    def get_challenge(challenge_id: int):
        result = challenge_store.export_challenge(challenge_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Challenge not found.")
        return result

    @app.get("/challenges/{challenge_id}/solution")
    def reveal_solution(challenge_id: int):
        result = challenge_store.reveal_solution(challenge_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Challenge not found.")
        return result

    return app


app = create_app()
