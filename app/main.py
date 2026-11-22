import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from google.genai import errors
from pydantic import ValidationError

from app.gemini import TIMEOUT_SECONDS, MissingAPIKey, generate_brief
from app.schemas import AnalyzeRequest, IncidentBrief


app = FastAPI(title="kube-incident-brief", version="0.1.0")
BriefGenerator = Callable[[list[str]], Awaitable[str | None]]


def get_brief_generator() -> BriefGenerator:
    return generate_brief


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default validation response includes input values (possibly logs).
    return JSONResponse(
        status_code=422,
        content={"detail": [
            {"loc": error["loc"], "msg": "Invalid request value", "type": error["type"]}
            for error in exc.errors()
        ]},
    )


@app.post("/incidents/analyze", response_model=IncidentBrief)
async def analyze_incident(
    request: AnalyzeRequest,
    generate: Annotated[BriefGenerator, Depends(get_brief_generator)],
) -> IncidentBrief:
    try:
        # Bound the entire provider operation as well as its HTTP transport.
        async with asyncio.timeout(TIMEOUT_SECONDS):
            raw_output = await generate(request.evidence)
    except MissingAPIKey:
        raise HTTPException(503, "Gemini is not configured. Set GEMINI_API_KEY.") from None
    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(504, "Gemini request timed out.") from None
    except errors.APIError as exc:
        if exc.code in (408, 504):
            raise HTTPException(504, "Gemini request timed out.") from None
        raise HTTPException(502, "Gemini request failed.") from None
    except Exception:
        # Never expose provider error messages, credentials, or submitted logs.
        raise HTTPException(502, "Gemini request failed.") from None

    try:
        return IncidentBrief.model_validate_json(
            raw_output, context={"evidence_count": len(request.evidence)}
        )
    except (ValidationError, TypeError):
        raise HTTPException(502, "Gemini returned an invalid incident brief.") from None
