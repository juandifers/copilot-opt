from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from product.api.routes import instances as instances_routes
from product.api.routes import metrics as metrics_routes
from product.api.routes import prompts as prompts_routes
from product.api.routes import results as results_routes
from product.api.routes import visual as visual_routes

app = FastAPI(
    title="VRPTW Copilot API",
    description="Read-only API exposing Run 1 artifacts to the dashboard frontend.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(results_routes.router)
app.include_router(prompts_routes.router)
app.include_router(metrics_routes.router)
app.include_router(instances_routes.router)
app.include_router(visual_routes.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
