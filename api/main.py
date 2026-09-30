from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
import os
import sys
import uvicorn


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from api import demo_access

# The route modules are underscore-prefixed so Vercel does not deploy each as a function of its
# own: it turns every api/*.py defining `app` into one, except names starting with "_". Unprefixed,
# /api/chat was served straight from api/chat.py, never passing the demo-password middleware
# below, and the project outgrew the Hobby plan's 12-function cap. Now every /api/* request is
# rewritten to api/index.py (vercel.json) and reaches this app. A new route module needs the
# prefix too.
from api._chat import app as chat_app
from api._followups import app as followups_app
from api._scraping import app as scraping_app
from api._fuelix import app as fuelix_app
from api._translate import app as translate_app
from api._cron import app as cron_app
from api._resource_links import app as resource_links_app
from api._admin_pipeline import app as admin_pipeline_app
from api._research_log import app as research_log_app


app = FastAPI(title="Concussio API")


def _copy_api_routes(source: FastAPI) -> None:
    for route in source.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/"):
            continue
        app.add_api_route(
            path=route.path,
            endpoint=route.endpoint,
            methods=list(route.methods or []),
            name=route.name,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            responses=route.responses,
            deprecated=route.deprecated,
            operation_id=route.operation_id,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
            response_model_exclude_unset=route.response_model_exclude_unset,
            response_model_exclude_defaults=route.response_model_exclude_defaults,
            response_model_exclude_none=route.response_model_exclude_none,
            include_in_schema=route.include_in_schema,
            response_class=route.response_class,
            openapi_extra=route.openapi_extra,
        )


for sub_app in (
    chat_app, followups_app, scraping_app, fuelix_app, translate_app, cron_app,
    resource_links_app, admin_pipeline_app, research_log_app,
):
    _copy_api_routes(sub_app)


@app.middleware("http")
async def enforce_demo_access(request: Request, call_next):
    """Gate the chatbot endpoints on the same password the pages ask for.

    Applied to the unified app rather than to each sub-app: routes are copied in above, so one
    check here covers every path a request can actually reach. Which paths those are lives in
    `api/demo_access.py`.
    """
    denial = demo_access.denial_for(
        request.url.path, request.cookies.get(demo_access.COOKIE_NAME)
    )
    if denial is not None:
        status, message = denial
        return JSONResponse({"detail": message}, status_code=status)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        env_file=os.path.join(PROJECT_ROOT, ".env"),
    )
