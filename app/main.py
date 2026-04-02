"""REE Receipt Oracle — FastAPI entrypoint."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routes.quote import router as quote_router
from .routes.verify import _x402_server, router as verify_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # initialize() is sync (calls get_supported() via HTTP); run in thread to avoid blocking loop
    await asyncio.to_thread(_x402_server.initialize)
    yield


app = FastAPI(
    title="REE Receipt Oracle",
    description="Pay-per-verification service for Gensyn REE receipts using x402.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(quote_router)
app.include_router(verify_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
