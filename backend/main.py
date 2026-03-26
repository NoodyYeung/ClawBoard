from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.tasks import router as tasks_router
from routers.calendar import router as calendar_router
from routers.projects import router as projects_router
from routers.dispatch import router as dispatch_router
from routers.github import router as github_router
from routers.monitor import router as monitor_router
from routers.settings import router as settings_router
from routers.project_settings import router as project_settings_router

app = FastAPI(title="ClawBoard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(calendar_router)
app.include_router(projects_router)
app.include_router(dispatch_router)
app.include_router(github_router)
app.include_router(monitor_router)
app.include_router(settings_router)
app.include_router(project_settings_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "clawboard-api"}
