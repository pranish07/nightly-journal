from __future__ import annotations

from secrets import compare_digest

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.dependencies import SessionDep
from app.jobs import claim_job, run_claimed_job
from app.scheduler import due_jobs
from app.timeutils import local_now

router = APIRouter()


@router.api_route("/cron/tick", methods=["GET", "POST"])
def tick(
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> JSONResponse:
    settings = request.app.state.settings
    provided = request.headers.get("x-cron-secret", "")
    if not compare_digest(provided, settings.cron_secret):
        return JSONResponse({"detail": "forbidden"}, status_code=403)

    now = request.app.state.clock()
    local_dt = local_now(now)
    claimed: list[dict[str, object]] = []

    for job in due_jobs(local_dt):
        claim = claim_job(session, job.kind, job.local_date, now)
        if claim is None:
            continue
        background_tasks.add_task(
            run_claimed_job,
            request.app.state.session_factory,
            settings,
            request.app.state.mailer,
            claim.kind,
            claim.local_date,
            request.app.state.clock,
            request.app.state.gemini_client,
        )
        claimed.append(
            {
                "kind": claim.kind,
                "local_date": claim.local_date.isoformat(),
                "attempts": claim.attempts,
            }
        )

    return JSONResponse(
        {
            "claimed": claimed,
            "local_time": local_dt.isoformat(),
        },
        status_code=202,
    )
