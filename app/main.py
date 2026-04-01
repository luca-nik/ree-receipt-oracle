"""REE Receipt Oracle — FastAPI entrypoint."""

from fastapi import FastAPI

from .routes.quote import router as quote_router
from .routes.verify import router as verify_router

app = FastAPI(
    title="REE Receipt Oracle",
    description="Pay-per-verification service for Gensyn REE receipts using x402.",
    version="0.1.0",
)

app.include_router(quote_router)
app.include_router(verify_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
