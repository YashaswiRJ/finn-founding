import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import current_investor
from app.config import settings
from app.database import db
from app.network import orgs as network_orgs
from app.network import repo as network_repo
from app.network import seed as network_seed
from app.routes import network, pull, push
from app.announcements import service as announcements_service
from app.services import companies, refresh, snapshot

log = logging.getLogger("finn")


def _scheduler(every_min: int) -> None:
    """Periodic refresh for hosts that stay awake. Off unless AUTO_REFRESH_MINUTES is set."""
    while True:
        time.sleep(every_min * 60)
        try:
            refresh.run(days=3)
        except Exception as e:
            log.warning("Scheduled refresh failed: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.connect()
    loaded = snapshot.load_if_empty()
    if loaded:
        log.info("Booted from seed snapshot: %s", loaded)
    companies.seed_defaults()
    announcements_service.retriage_unread()
    network_orgs.seed_from_companies()
    network_seed.load_demo_if_empty()
    network_repo.purge_expired()
    if settings.auto_refresh_minutes > 0:
        threading.Thread(target=_scheduler, args=(settings.auto_refresh_minutes,), daemon=True).start()
    yield


app = FastAPI(title="FINN API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(push.router)
app.include_router(pull.router)
app.include_router(network.router)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "llm_configured": bool(settings.anthropic_api_key) and settings.llm_enabled,
        "companies": db.query_one("SELECT COUNT(*) n FROM companies")["n"],
        "snapshot": db.kv_get("snapshot_loaded"),
        "auto_refresh_minutes": settings.auto_refresh_minutes,
        "network": {"demo_mode": settings.network_demo_mode,
                    "public_profiles": db.query_one("SELECT COUNT(*) n FROM people WHERE owner_id IS NULL")["n"]},
    }


@app.get("/api/me")
def me(owner: str = Depends(current_investor)):
    inv = network_repo.investor(owner) or {}
    return {"investor_id": owner, "display_name": inv.get("display_name"), "demo": owner == settings.demo_investor_id
            and settings.network_demo_mode, "consent_accepted_at": inv.get("consent_accepted_at"),
            "retention_days": inv.get("retention_days"), **network_repo.counts(owner)}
