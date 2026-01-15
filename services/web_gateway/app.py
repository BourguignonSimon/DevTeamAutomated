"""Web Gateway API for project tracking and orchestrator interaction.

This FastAPI application serves as the web interface gateway, providing:
- Project creation with unique tracking IDs
- Prompt-based interaction with the orchestrator
- Question/clarification handling
- Customer message delivery
- Project status monitoring
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:
    from services.order_intake_agent.fastapi_compat import (
        FastAPI,
        File,
        Form,
        HTTPException,
        JSONResponse,
        status,
        UploadFile,
    )
    CORSMiddleware = None
    StaticFiles = None
    BaseModel = object

from core.backlog_store import BacklogStore
from core.config import Settings
from core.event_utils import envelope
from core.project_store import (
    CustomerMessage,
    Interaction,
    ProjectInfo,
    ProjectStatus,
    ProjectStore,
    generate_project_id,
)
from core.question_store import QuestionStore
from core.redis_streams import build_redis_client

log = logging.getLogger("web_gateway")


# -------------------------
# Pydantic Models
# -------------------------
class ProjectInitRequest(BaseModel):
    """Request model for project initialization."""
    project_name: str
    request_text: str
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PromptRequest(BaseModel):
    """Request model for sending a prompt to the orchestrator."""
    project_id: str
    prompt: str
    context: Optional[Dict[str, Any]] = None


class AnswerRequest(BaseModel):
    """Request model for answering a question."""
    question_id: str
    answer: str
    project_id: Optional[str] = None


class MessageResponseRequest(BaseModel):
    """Request model for responding to a customer message."""
    message_id: str
    response: str


# -------------------------
# Settings
# -------------------------
@dataclass
class WebGatewaySettings:
    """Settings for the web gateway service."""
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    namespace: str = os.getenv("NAMESPACE", "audit")
    stream_name: str = os.getenv("STREAM_NAME", "")
    key_prefix: str = os.getenv("KEY_PREFIX", "")
    service_name: str = "web_gateway"
    cors_origins: List[str] = None

    def __post_init__(self) -> None:
        namespace = (self.namespace or "audit").strip(":")
        if not self.stream_name:
            self.stream_name = f"{namespace}:events"
        if not self.key_prefix:
            self.key_prefix = namespace
        if self.cors_origins is None:
            origins = os.getenv("CORS_ORIGINS", "*")
            self.cors_origins = [o.strip() for o in origins.split(",")]


# -------------------------
# Dependencies
# -------------------------
class Dependencies:
    """Dependency container for the web gateway."""

    def __init__(self, settings: WebGatewaySettings, r: redis.Redis):
        self.settings = settings
        self.redis = r
        self.project_store = ProjectStore(r, prefix=settings.key_prefix)
        self.backlog_store = BacklogStore(r, prefix=settings.key_prefix)
        self.question_store = QuestionStore(r, prefix=settings.key_prefix)
        self.logs: List[Dict[str, Any]] = []


def get_deps() -> Dependencies:
    """Create dependencies for production use."""
    settings = WebGatewaySettings()
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)
    return Dependencies(settings, r)


# -------------------------
# App Factory
# -------------------------
def create_app(deps: Dependencies | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    deps = deps or get_deps()
    app = FastAPI(
        title="Project Tracking Web Gateway",
        description="API for project tracking and orchestrator interaction",
        version="1.0.0",
    )

    # Add CORS middleware if available
    if CORSMiddleware is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=deps.settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # -------------------------
    # Project Endpoints
    # -------------------------
    @app.post("/api/project/init")
    async def init_project(
        project_name: str = Form(...),
        request_text: str = Form(...),
        requester_name: Optional[str] = Form(None),
        requester_email: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
    ) -> JSONResponse:
        """Initialize a new project with a unique tracking ID.

        This creates a new project, generates a unique ID for tracking,
        and sends the initial request to the orchestrator.
        """
        project_id = generate_project_id()
        requester = {}
        if requester_name:
            requester["name"] = requester_name
        if requester_email:
            requester["email"] = requester_email
        if not requester:
            requester = {"name": "web_user"}

        # Handle file upload if present
        file_info = None
        if file and file.filename:
            artifact_id = str(uuid.uuid4())
            file_content = await file.read()
            file_info = {
                "artifact_id": artifact_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(file_content),
            }
            # Store file reference in Redis
            deps.redis.setex(
                f"{deps.settings.key_prefix}:artifact:{artifact_id}",
                3600,  # 1 hour TTL
                file_content,
            )

        # Create project in store
        project = deps.project_store.create_project(
            name=project_name,
            description=request_text,
            requester=requester,
            metadata={"file": file_info} if file_info else {},
            project_id=project_id,
        )

        # Record initial interaction
        deps.project_store.add_interaction(
            project_id=project_id,
            interaction_type="user_input",
            content=request_text,
            metadata={"source": "init_form", "file": file_info},
        )

        # Emit PROJECT.INITIAL_REQUEST_RECEIVED event
        correlation_id = str(uuid.uuid4())
        env = envelope(
            event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
            payload={
                "project_id": project_id,
                "request_text": request_text,
                "requester": requester,
                "file_info": file_info,
            },
            source=deps.settings.service_name,
            correlation_id=correlation_id,
            causation_id=None,
        )
        redis_id = deps.redis.xadd(deps.settings.stream_name, {"event": json.dumps(env)})

        _log_event(deps, "info", f"Project created: {project_id}")

        return JSONResponse({
            "project_id": project_id,
            "status": project.status,
            "event_id": env["event_id"],
            "redis_id": redis_id,
            "message": "Project created successfully. The orchestrator will process your request.",
        })

    @app.post("/api/project/{project_id}/prompt")
    async def send_prompt(project_id: str, request: PromptRequest) -> JSONResponse:
        """Send a prompt to the orchestrator for an existing project.

        This allows continued interaction with the orchestrator
        while maintaining the project context.
        """
        project = deps.project_store.get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        # Record the interaction
        interaction = deps.project_store.add_interaction(
            project_id=project_id,
            interaction_type="user_input",
            content=request.prompt,
            metadata=request.context or {},
        )

        # Get context for the orchestrator
        context = deps.project_store.get_interaction_context(project_id, last_n=10)

        # Emit USER.PROMPT_SUBMITTED event
        correlation_id = str(uuid.uuid4())
        env = envelope(
            event_type="USER.PROMPT_SUBMITTED",
            payload={
                "project_id": project_id,
                "prompt": request.prompt,
                "interaction_id": interaction.id,
                "context": context,
            },
            source=deps.settings.service_name,
            correlation_id=correlation_id,
            causation_id=None,
        )
        redis_id = deps.redis.xadd(deps.settings.stream_name, {"event": json.dumps(env)})

        _log_event(deps, "info", f"Prompt submitted for project {project_id}")

        return JSONResponse({
            "project_id": project_id,
            "interaction_id": interaction.id,
            "event_id": env["event_id"],
            "message": "Prompt sent to orchestrator",
        })

    @app.get("/api/project/{project_id}/status")
    async def get_project_status(project_id: str) -> JSONResponse:
        """Get the current status of a project."""
        project = deps.project_store.get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        # Calculate comprehensive status
        status_info = deps.project_store.calculate_project_status(
            project_id,
            deps.backlog_store,
        )

        return JSONResponse(status_info)

    @app.get("/api/project/{project_id}/interactions")
    async def get_project_interactions(
        project_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        """Get interaction history for a project."""
        project = deps.project_store.get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        interactions = deps.project_store.get_interactions(
            project_id,
            limit=limit,
            offset=offset,
        )

        return JSONResponse({
            "project_id": project_id,
            "interactions": [i.to_dict() for i in interactions],
            "count": len(interactions),
        })

    @app.get("/api/projects")
    async def list_projects() -> JSONResponse:
        """List all projects."""
        project_ids = deps.project_store.list_projects()
        projects = []
        for pid in project_ids:
            project = deps.project_store.get_project(pid)
            if project:
                projects.append(project.to_dict())

        return JSONResponse({
            "projects": projects,
            "count": len(projects),
        })

    # -------------------------
    # Question/Clarification Endpoints
    # -------------------------
    @app.get("/api/questions")
    async def get_questions(
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> JSONResponse:
        """Get questions, optionally filtered by status and project."""
        questions = []

        # If project_id specified, get questions for that project
        if project_id:
            project_ids = [project_id]
        else:
            # Get all projects
            project_ids = deps.project_store.list_projects()

        for pid in project_ids:
            if status == "open":
                question_ids = deps.question_store.list_open(pid)
            else:
                question_ids = deps.question_store.list_all(pid)

            for qid in question_ids:
                q = deps.question_store.get_question(pid, qid)
                if q:
                    questions.append(q)

        return JSONResponse({
            "questions": questions,
            "count": len(questions),
        })

    @app.post("/api/questions/answer")
    async def answer_question(request: AnswerRequest) -> JSONResponse:
        """Submit an answer to a question.

        This records the answer and notifies the orchestrator
        to unblock the related task.
        """
        question_id = request.question_id
        answer = request.answer

        # Find the question across projects if project_id not provided
        project_id = request.project_id
        question = None

        if project_id:
            question = deps.question_store.get_question(project_id, question_id)
        else:
            # Search all projects
            for pid in deps.project_store.list_projects():
                q = deps.question_store.get_question(pid, question_id)
                if q:
                    question = q
                    project_id = pid
                    break

        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Question {question_id} not found",
            )

        # Record the answer interaction
        deps.project_store.add_interaction(
            project_id=project_id,
            interaction_type="user_input",
            content=f"Answer to question {question_id}: {answer}",
            metadata={"question_id": question_id, "answer": answer},
        )

        # Emit USER.ANSWER_SUBMITTED event
        correlation_id = question.get("correlation_id") or str(uuid.uuid4())
        env = envelope(
            event_type="USER.ANSWER_SUBMITTED",
            payload={
                "project_id": project_id,
                "question_id": question_id,
                "answer": answer,
                "backlog_item_id": question.get("backlog_item_id"),
            },
            source=deps.settings.service_name,
            correlation_id=correlation_id,
            causation_id=None,
        )
        redis_id = deps.redis.xadd(deps.settings.stream_name, {"event": json.dumps(env)})

        _log_event(deps, "info", f"Answer submitted for question {question_id}")

        return JSONResponse({
            "question_id": question_id,
            "project_id": project_id,
            "status": "answered",
            "event_id": env["event_id"],
            "message": "Answer submitted successfully",
        })

    # -------------------------
    # Customer Messages Endpoints
    # -------------------------
    @app.get("/api/project/{project_id}/messages")
    async def get_customer_messages(
        project_id: str,
        unread_only: bool = False,
    ) -> JSONResponse:
        """Get messages from the orchestrator for this project."""
        project = deps.project_store.get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
            )

        messages = deps.project_store.get_customer_messages(
            project_id,
            unread_only=unread_only,
        )

        return JSONResponse({
            "project_id": project_id,
            "messages": [m.to_dict() for m in messages],
            "count": len(messages),
        })

    @app.post("/api/project/{project_id}/messages/{message_id}/read")
    async def mark_message_read(project_id: str, message_id: str) -> JSONResponse:
        """Mark a message as read."""
        deps.project_store.mark_message_read(project_id, message_id)
        return JSONResponse({"status": "ok", "message_id": message_id})

    @app.post("/api/project/{project_id}/messages/{message_id}/respond")
    async def respond_to_message(
        project_id: str,
        message_id: str,
        request: MessageResponseRequest,
    ) -> JSONResponse:
        """Respond to a message from the orchestrator."""
        message = deps.project_store.respond_to_message(
            project_id,
            message_id,
            request.response,
        )

        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message {message_id} not found",
            )

        # Record the response as an interaction
        deps.project_store.add_interaction(
            project_id=project_id,
            interaction_type="user_input",
            content=f"Response to message {message_id}: {request.response}",
            metadata={"message_id": message_id, "response": request.response},
        )

        # Emit CUSTOMER.MESSAGE_RESPONDED event
        correlation_id = str(uuid.uuid4())
        env = envelope(
            event_type="CUSTOMER.MESSAGE_RESPONDED",
            payload={
                "project_id": project_id,
                "message_id": message_id,
                "response": request.response,
                "related_item_id": message.related_item_id,
            },
            source=deps.settings.service_name,
            correlation_id=correlation_id,
            causation_id=None,
        )
        deps.redis.xadd(deps.settings.stream_name, {"event": json.dumps(env)})

        return JSONResponse({
            "status": "ok",
            "message_id": message_id,
            "response_recorded": True,
        })

    # -------------------------
    # Logs Endpoint
    # -------------------------
    @app.get("/api/logs")
    async def get_logs(
        level: Optional[str] = None,
        limit: int = 100,
    ) -> JSONResponse:
        """Get system logs for the web interface."""
        logs = deps.logs[-limit:]
        if level:
            logs = [l for l in logs if l.get("level") == level]
        return JSONResponse({"logs": logs})

    # -------------------------
    # Health Check
    # -------------------------
    @app.get("/api/health")
    async def health_check() -> JSONResponse:
        """Health check endpoint."""
        try:
            deps.redis.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "disconnected"

        return JSONResponse({
            "status": "ok",
            "redis": redis_status,
            "service": deps.settings.service_name,
        })

    return app


def _log_event(deps: Dependencies, level: str, message: str) -> None:
    """Add a log entry."""
    entry = {
        "level": level,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    deps.logs.append(entry)
    # Keep only last 1000 logs
    if len(deps.logs) > 1000:
        deps.logs = deps.logs[-1000:]
    log.log(getattr(logging, level.upper(), logging.INFO), message)


# Create app instance for uvicorn
app = create_app()


def main() -> None:
    """Run the web gateway server."""
    import uvicorn

    port = int(os.getenv("WEB_GATEWAY_PORT", "8000"))
    host = os.getenv("WEB_GATEWAY_HOST", "0.0.0.0")
    log.info(f"Starting web gateway on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    main()
