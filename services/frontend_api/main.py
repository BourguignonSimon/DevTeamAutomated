"""Frontend API Gateway - Simple HTTP API for the web interface.

This service provides:
- Static file serving for the frontend (index.html, app.js)
- REST API endpoints for project management, questions, and logs
- Redis integration for state persistence
- Event publishing to orchestrator via Redis Streams
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from core.backlog_store import BacklogStore
from core.config import Settings
from core.question_store import QuestionStore

log = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================


class ProjectInitResponse(BaseModel):
    project_id: str
    status: str


class QuestionResponse(BaseModel):
    question_id: str
    backlog_item_id: str
    question_text: str
    answer_type: str
    status: str
    project_id: Optional[str] = None


class AnswerRequest(BaseModel):
    question_id: str
    answer: str


class AnswerResponse(BaseModel):
    status: str


class ProjectStatusResponse(BaseModel):
    state: str
    completion_percentage: float
    blocked_items: int
    total_items: int


class StopProjectResponse(BaseModel):
    status: str
    stopped_items: int


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    source: str = "system"


# ============================================================================
# Event Helpers
# ============================================================================


def now_iso() -> str:
    """Generate ISO timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def create_event_envelope(
    event_type: str,
    payload: Dict[str, Any],
    source: str = "frontend_api",
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an event envelope for publishing to Redis Streams."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "timestamp": now_iso(),
        "source": {
            "service": source,
            "instance": os.getenv("HOSTNAME", f"{source}-1"),
        },
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "causation_id": causation_id,
        "payload": payload,
    }


# ============================================================================
# Application Factory
# ============================================================================


def get_redis_client(settings: Settings) -> redis.Redis:
    """Create Redis client from settings."""
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=False,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = settings or Settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    app = FastAPI(
        title="DevTeam Automated - Frontend API",
        description="Simple API gateway for the web interface",
        version="1.0.0",
    )

    # CORS middleware for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Redis and stores
    r = get_redis_client(settings)
    backlog_store = BacklogStore(r, prefix=settings.key_prefix)
    question_store = QuestionStore(r, prefix=settings.key_prefix)

    # Stream name for orchestrator events
    stream_name = settings.stream_name

    # In-memory log storage (for simplicity)
    logs_storage: List[Dict[str, Any]] = []

    def add_log(message: str, level: str = "info", source: str = "api") -> None:
        """Add a log entry to storage."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "source": source,
        }
        logs_storage.insert(0, entry)
        # Keep only last 500 logs
        if len(logs_storage) > 500:
            logs_storage.pop()

    def publish_event(event_type: str, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> str:
        """Publish an event to the Redis Stream for the orchestrator."""
        envelope = create_event_envelope(
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
        )
        event_json = json.dumps(envelope)
        r.xadd(stream_name, {"event": event_json})
        add_log(f"Published {event_type} event", "info", "orchestrator")
        return envelope["correlation_id"]

    # ========================================================================
    # Health Check
    # ========================================================================

    @app.get("/health")
    def health() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    # ========================================================================
    # Project Endpoints
    # ========================================================================

    @app.post("/api/project/init", response_model=ProjectInitResponse)
    async def init_project(
        project_name: str = Form(...),
        request_text: str = Form(...),
        file: Optional[UploadFile] = File(None),
    ) -> ProjectInitResponse:
        """Initialize a new project and send request to orchestrator."""
        project_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())

        # Create initial backlog item representing the project
        initial_item = {
            "id": project_id,
            "project_id": project_id,
            "title": project_name,
            "description": request_text,
            "status": "CREATED",
            "item_type": "project_root",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        # Store file content if provided
        if file:
            try:
                content = await file.read()
                initial_item["attachment_name"] = file.filename
                initial_item["attachment_size"] = len(content)
                # Store file in Redis
                file_key = f"{settings.key_prefix}:project:{project_id}:attachment"
                r.set(file_key, content)
                add_log(f"File '{file.filename}' uploaded for project {project_id}", "info")
            except Exception as e:
                log.warning(f"Failed to process uploaded file: {e}")

        # Save project to backlog store
        backlog_store.put_item(initial_item)
        add_log(f"Project '{project_name}' created with ID {project_id}", "info")

        # Publish PROJECT.INITIAL_REQUEST_RECEIVED event to orchestrator
        publish_event(
            event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
            payload={
                "project_id": project_id,
                "request_text": request_text,
            },
            correlation_id=correlation_id,
        )

        return ProjectInitResponse(project_id=project_id, status="CREATED")

    @app.get("/api/project/{project_id}/status", response_model=ProjectStatusResponse)
    def get_project_status(project_id: str) -> ProjectStatusResponse:
        """Get the current status of a project."""
        # Get all items for this project
        item_ids = backlog_store.list_item_ids(project_id)

        if not item_ids:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        total_items = len(item_ids)
        completed_items = len(backlog_store.list_item_ids_by_status(project_id, "DONE"))
        completed_items += len(backlog_store.list_item_ids_by_status(project_id, "COMPLETED"))
        blocked_items = len(backlog_store.list_item_ids_by_status(project_id, "BLOCKED"))
        stopped_items = len(backlog_store.list_item_ids_by_status(project_id, "STOPPED"))
        in_progress_items = len(backlog_store.list_item_ids_by_status(project_id, "IN_PROGRESS"))

        # Calculate completion percentage
        completion = (completed_items / total_items * 100) if total_items > 0 else 0

        # Determine overall state
        if stopped_items > 0:
            state = "STOPPED"
        elif blocked_items > 0:
            state = "BLOCKED"
        elif completed_items == total_items:
            state = "COMPLETED"
        elif in_progress_items > 0 or completed_items > 0:
            state = "IN_PROGRESS"
        else:
            state = "CREATED"

        return ProjectStatusResponse(
            state=state,
            completion_percentage=round(completion, 1),
            blocked_items=blocked_items,
            total_items=total_items,
        )

    @app.post("/api/project/{project_id}/stop", response_model=StopProjectResponse)
    def stop_project(project_id: str) -> StopProjectResponse:
        """Stop a project and cancel all pending work items."""
        item_ids = backlog_store.list_item_ids(project_id)

        if not item_ids:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        stopped_count = 0
        for item_id in item_ids:
            item = backlog_store.get_item(project_id, item_id)
            if item and item.get("status") not in ("DONE", "COMPLETED", "STOPPED"):
                item["status"] = "STOPPED"
                backlog_store.put_item(item)
                stopped_count += 1

        add_log(f"Project {project_id} stopped. {stopped_count} items cancelled.", "warn")

        return StopProjectResponse(status="stopped", stopped_items=stopped_count)

    @app.get("/api/projects")
    def list_projects() -> List[Dict[str, Any]]:
        """List all projects."""
        project_ids = backlog_store.list_project_ids()
        projects = []
        for pid in project_ids:
            root_item = backlog_store.get_item(pid, pid)
            if root_item:
                projects.append({
                    "project_id": pid,
                    "title": root_item.get("title", "Untitled"),
                    "status": root_item.get("status", "UNKNOWN"),
                    "created_at": root_item.get("created_at", ""),
                })
        return projects

    # ========================================================================
    # Question Endpoints
    # ========================================================================

    @app.get("/api/questions")
    def get_questions(
        status: str = Query("open"),
        project_id: Optional[str] = Query(None),
    ) -> List[QuestionResponse]:
        """Get questions filtered by status and optionally by project."""
        questions = []

        # Get project IDs to search
        if project_id:
            project_ids = [project_id]
        else:
            project_ids = backlog_store.list_project_ids()

        for pid in project_ids:
            if status.lower() == "open":
                question_ids = question_store.list_open(pid)
            else:
                question_ids = question_store.list_all(pid)

            for qid in question_ids:
                q = question_store.get_question(pid, qid)
                if q:
                    questions.append(
                        QuestionResponse(
                            question_id=q["id"],
                            backlog_item_id=q.get("backlog_item_id", ""),
                            question_text=q.get("question_text", ""),
                            answer_type=q.get("answer_type", "text"),
                            status=q.get("status", "OPEN"),
                            project_id=pid,
                        )
                    )

        return questions

    @app.post("/api/questions/answer", response_model=AnswerResponse)
    def answer_question(req: AnswerRequest) -> AnswerResponse:
        """Submit an answer to a question and notify orchestrator."""
        # Find the question across all projects
        project_ids = backlog_store.list_project_ids()
        found_project_id = None

        for project_id in project_ids:
            q = question_store.get_question(project_id, req.question_id)
            if q:
                # Store the answer
                question_store.set_answer(project_id, req.question_id, req.answer)
                question_store.close_question(project_id, req.question_id)
                found_project_id = project_id
                add_log(f"Question {req.question_id} answered", "info")

                # Publish USER.ANSWER_SUBMITTED event to orchestrator
                publish_event(
                    event_type="USER.ANSWER_SUBMITTED",
                    payload={
                        "project_id": project_id,
                        "question_id": req.question_id,
                        "answer": req.answer,
                    },
                    correlation_id=q.get("correlation_id"),
                )
                break

        if not found_project_id:
            raise HTTPException(status_code=404, detail=f"Question {req.question_id} not found")

        return AnswerResponse(status="ok")

    @app.post("/api/questions/create")
    def create_question(
        project_id: str = Form(...),
        backlog_item_id: str = Form(...),
        question_text: str = Form(...),
        answer_type: str = Form("text"),
    ) -> QuestionResponse:
        """Create a new question (for testing/demo purposes)."""
        q = question_store.create_question(
            project_id=project_id,
            backlog_item_id=backlog_item_id,
            question_text=question_text,
            answer_type=answer_type,
        )
        add_log(f"Question created for project {project_id}", "info")
        return QuestionResponse(
            question_id=q["id"],
            backlog_item_id=backlog_item_id,
            question_text=question_text,
            answer_type=answer_type,
            status="OPEN",
            project_id=project_id,
        )

    # ========================================================================
    # Logs Endpoint
    # ========================================================================

    @app.get("/api/logs")
    def get_logs(limit: int = 100) -> List[Dict[str, Any]]:
        """Get system logs."""
        return logs_storage[:limit]

    # ========================================================================
    # Static Files & Frontend
    # ========================================================================

    # Determine the project root (where index.html is)
    project_root = Path(__file__).parent.parent.parent

    @app.get("/", response_class=HTMLResponse)
    def serve_index() -> FileResponse:
        """Serve the main index.html file."""
        index_path = project_root / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend not found")
        return FileResponse(index_path)

    @app.get("/app.js")
    def serve_app_js() -> FileResponse:
        """Serve the main app.js file."""
        js_path = project_root / "app.js"
        if not js_path.exists():
            raise HTTPException(status_code=404, detail="app.js not found")
        return FileResponse(js_path, media_type="application/javascript")

    # Add startup log
    add_log("Frontend API Gateway started", "info", "system")
    add_log(f"Publishing events to stream: {stream_name}", "info", "system")

    return app


# Create the default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
