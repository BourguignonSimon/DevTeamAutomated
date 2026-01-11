from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import redis

try:  # pragma: no cover - prefer real FastAPI when available
    from fastapi import FastAPI, File, HTTPException, UploadFile, status
    from fastapi.params import Form
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - fall back to lightweight stub for offline environments
    from services.order_intake_agent.fastapi_compat import (  # type: ignore
        FastAPI,
        File,
        Form,
        HTTPException,
        JSONResponse,
        TestClient,
        UploadFile,
        status,
    )

from core.event_utils import envelope, now_iso
from core.redis_streams import build_redis_client
from services.order_intake_agent.settings import OrderIntakeSettings
from services.order_intake_agent.store import OrderStore


class Dependencies:
    def __init__(self, settings: OrderIntakeSettings, r: redis.Redis):
        self.settings = settings
        self.redis = r
        self.store = OrderStore(r, prefix=settings.orders_prefix, storage_dir=settings.storage_dir)


def get_deps():  # pragma: no cover - runtime dependency
    settings = OrderIntakeSettings()
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)
    return Dependencies(settings, r)


def create_app(deps: Dependencies | None = None) -> FastAPI:
    deps = deps or get_deps()
    app = FastAPI()

    @app.post("/orders/inbox")
    async def ingest_order(
        from_email: str = Form(...),
        subject: str = Form(...),
        customer_hint: str | None = Form(None),
        delivery_address: str | None = Form(None),
        delivery_date: str | None = Form(None),
        files: list[UploadFile] = File(...),
    ) -> JSONResponse:
        order_id = str(uuid.uuid4())
        received_at = datetime.now(timezone.utc).isoformat()
        attachments = []
        for uploaded in files:
            artifact_id = str(uuid.uuid4())
            target = deps.store.artifact_path(order_id, artifact_id, uploaded.filename)
            content = await uploaded.read()
            target.write_bytes(content)
            meta = {"artifact_id": artifact_id, "filename": uploaded.filename, "mime_type": uploaded.content_type, "path": str(target)}
            deps.store.save_artifact_metadata(artifact_id, meta, deps.settings.artifact_ttl_s)
            attachments.append({"artifact_id": artifact_id, "filename": uploaded.filename, "mime_type": uploaded.content_type})

        env = envelope(
            event_type="ORDER.INBOX_RECEIVED",
            payload={
                "order_id": order_id,
                "from_email": from_email,
                "subject": subject,
                "received_at": received_at,
                "attachments": attachments,
                "customer_hint": customer_hint,
                "delivery_address": delivery_address,
                "delivery_date": delivery_date,
            },
            source=deps.settings.service_name,
            correlation_id=str(uuid.uuid4()),
            causation_id=None,
        )
        redis_id = deps.redis.xadd(deps.settings.stream_name, {"event": json.dumps(env)})
        return JSONResponse({"order_id": order_id, "event_id": env["event_id"], "redis_id": redis_id})

    @app.get("/orders/pending-validation")
    def pending_validation():
        return {"orders": deps.store.list_pending_validation(deps.settings.validation_set_key)}

    @app.post("/orders/{order_id}/validate")
    def validate_order(order_id: str, corrections: Dict[str, Any]):
        draft = deps.store.get_order_draft(order_id)
        if not draft:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
        merged_draft = {**draft, **corrections}
        if "delivery" in corrections and isinstance(draft.get("delivery"), dict):
            merged_draft["delivery"] = {**draft.get("delivery", {}), **corrections.get("delivery", {})}
        deps.store.save_order_draft(order_id, merged_draft)
        env = envelope(
            event_type="ORDER.VALIDATED",
            payload={
                "order_id": order_id,
                "validated_by": "api",
                "validated_at": now_iso(),
                "final_order_draft": merged_draft,
            },
            source=deps.settings.service_name,
            correlation_id=str(uuid.uuid4()),
            causation_id=None,
        )
        deps.redis.xadd(deps.settings.stream_name, {"event": json.dumps(env)})
        deps.store.remove_pending_validation(deps.settings.validation_set_key, order_id)
        return {"status": "ok", "event_id": env["event_id"]}

    return app


app = create_app()  # pragma: no cover


def get_test_client(deps: Dependencies) -> TestClient:
    return TestClient(create_app(deps))
