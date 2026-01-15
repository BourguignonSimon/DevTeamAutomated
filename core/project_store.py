"""Redis-backed store for Project tracking with unique IDs.

This module provides project lifecycle management for the web interface,
enabling unique project ID generation and interaction context tracking.

Storage:
  - project doc:    {prefix}:project:{project_id}:info
  - projects index: {prefix}:projects:all
  - interactions:   {prefix}:project:{project_id}:interactions
  - messages:       {prefix}:project:{project_id}:messages
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import redis


class ProjectStatus(str, Enum):
    """Project lifecycle states."""
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ProjectInfo:
    """Project metadata and tracking information."""
    id: str
    name: str
    description: str
    status: str = ProjectStatus.CREATED.value
    created_at: str = ""
    updated_at: str = ""
    requester: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    completion_percentage: int = 0
    blocked_items: int = 0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()
        if not self.updated_at:
            self.updated_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Interaction:
    """Represents a single interaction with the orchestrator."""
    id: str
    project_id: str
    type: str  # "user_input", "system_response", "clarification_request", "task_update"
    content: str
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Interaction":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CustomerMessage:
    """Message from orchestrator to customer requiring attention."""
    id: str
    project_id: str
    message_type: str  # "clarification", "status_update", "task_assignment", "completion"
    content: str
    status: str = "UNREAD"  # UNREAD, READ, RESPONDED
    timestamp: str = ""
    related_item_id: Optional[str] = None
    requires_response: bool = False
    response: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomerMessage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def generate_project_id() -> str:
    """Generate a unique project tracking ID."""
    return str(uuid.uuid4())


class ProjectStore:
    """Redis-backed store for Project management."""

    def __init__(self, r: redis.Redis, prefix: str | None = None):
        self.r = r
        self.prefix = prefix or os.getenv("KEY_PREFIX", "audit")

    def _project_key(self, project_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:info"

    def _projects_index(self) -> str:
        return f"{self.prefix}:projects:all"

    def _interactions_key(self, project_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:interactions"

    def _messages_key(self, project_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:messages"

    def _unread_messages_key(self, project_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:messages:unread"

    @staticmethod
    def _decode(v) -> str:
        if isinstance(v, bytes):
            return v.decode("utf-8")
        return str(v)

    # -------------------------
    # Project CRUD
    # -------------------------
    def create_project(
        self,
        name: str,
        description: str,
        requester: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
    ) -> ProjectInfo:
        """Create a new project with a unique tracking ID."""
        pid = project_id or generate_project_id()
        project = ProjectInfo(
            id=pid,
            name=name,
            description=description,
            requester=requester or {},
            metadata=metadata or {},
        )
        self._save_project(project)
        return project

    def _save_project(self, project: ProjectInfo) -> None:
        """Save project to Redis."""
        project.updated_at = _now_iso()
        self.r.set(self._project_key(project.id), json.dumps(project.to_dict()))
        self.r.sadd(self._projects_index(), project.id)

    def get_project(self, project_id: str) -> Optional[ProjectInfo]:
        """Retrieve a project by ID."""
        raw = self.r.get(self._project_key(project_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return ProjectInfo.from_dict(json.loads(raw))

    def update_project_status(
        self,
        project_id: str,
        status: ProjectStatus,
        completion_percentage: Optional[int] = None,
        blocked_items: Optional[int] = None,
    ) -> Optional[ProjectInfo]:
        """Update project status and optional metrics."""
        project = self.get_project(project_id)
        if not project:
            return None
        project.status = status.value
        if completion_percentage is not None:
            project.completion_percentage = completion_percentage
        if blocked_items is not None:
            project.blocked_items = blocked_items
        self._save_project(project)
        return project

    def list_projects(self) -> List[str]:
        """List all project IDs."""
        return sorted([self._decode(x) for x in self.r.smembers(self._projects_index())])

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all related data."""
        if not self.get_project(project_id):
            return False
        self.r.delete(self._project_key(project_id))
        self.r.delete(self._interactions_key(project_id))
        self.r.delete(self._messages_key(project_id))
        self.r.delete(self._unread_messages_key(project_id))
        self.r.srem(self._projects_index(), project_id)
        return True

    # -------------------------
    # Interactions
    # -------------------------
    def add_interaction(
        self,
        project_id: str,
        interaction_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Interaction:
        """Record an interaction for context tracking."""
        interaction = Interaction(
            id=str(uuid.uuid4()),
            project_id=project_id,
            type=interaction_type,
            content=content,
            metadata=metadata or {},
        )
        self.r.rpush(
            self._interactions_key(project_id),
            json.dumps(interaction.to_dict()),
        )
        return interaction

    def get_interactions(
        self,
        project_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Interaction]:
        """Get interaction history for a project."""
        raw_list = self.r.lrange(self._interactions_key(project_id), offset, offset + limit - 1)
        interactions = []
        for raw in raw_list:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            interactions.append(Interaction.from_dict(json.loads(raw)))
        return interactions

    def get_interaction_context(self, project_id: str, last_n: int = 10) -> List[Dict[str, Any]]:
        """Get recent interaction context for AI processing."""
        interactions = self.get_interactions(project_id, limit=last_n)
        return [i.to_dict() for i in interactions[-last_n:]]

    # -------------------------
    # Customer Messages
    # -------------------------
    def send_message_to_customer(
        self,
        project_id: str,
        message_type: str,
        content: str,
        related_item_id: Optional[str] = None,
        requires_response: bool = False,
    ) -> CustomerMessage:
        """Send a message from orchestrator to customer."""
        message = CustomerMessage(
            id=str(uuid.uuid4()),
            project_id=project_id,
            message_type=message_type,
            content=content,
            related_item_id=related_item_id,
            requires_response=requires_response,
        )
        self.r.rpush(self._messages_key(project_id), json.dumps(message.to_dict()))
        self.r.sadd(self._unread_messages_key(project_id), message.id)
        return message

    def get_customer_messages(
        self,
        project_id: str,
        unread_only: bool = False,
    ) -> List[CustomerMessage]:
        """Get messages for a customer/project."""
        raw_list = self.r.lrange(self._messages_key(project_id), 0, -1)
        messages = []
        unread_ids = set()
        if unread_only:
            unread_ids = {
                self._decode(x)
                for x in self.r.smembers(self._unread_messages_key(project_id))
            }

        for raw in raw_list:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            msg = CustomerMessage.from_dict(json.loads(raw))
            if unread_only and msg.id not in unread_ids:
                continue
            messages.append(msg)
        return messages

    def mark_message_read(self, project_id: str, message_id: str) -> bool:
        """Mark a customer message as read."""
        self.r.srem(self._unread_messages_key(project_id), message_id)
        return True

    def respond_to_message(
        self,
        project_id: str,
        message_id: str,
        response: str,
    ) -> Optional[CustomerMessage]:
        """Record a customer's response to a message."""
        messages = self.get_customer_messages(project_id)
        for i, msg in enumerate(messages):
            if msg.id == message_id:
                msg.status = "RESPONDED"
                msg.response = response
                # Update in Redis list
                self.r.lset(
                    self._messages_key(project_id),
                    i,
                    json.dumps(msg.to_dict()),
                )
                self.mark_message_read(project_id, message_id)
                return msg
        return None

    # -------------------------
    # Status Calculation
    # -------------------------
    def calculate_project_status(
        self,
        project_id: str,
        backlog_store: Any,
    ) -> Dict[str, Any]:
        """Calculate comprehensive project status from backlog items."""
        project = self.get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        # Get backlog items for this project
        total_items = 0
        completed_items = 0
        blocked_items = 0
        in_progress_items = 0

        for item in backlog_store.iter_items(project_id):
            total_items += 1
            status = item.get("status", "")
            if status == "DONE":
                completed_items += 1
            elif status == "BLOCKED":
                blocked_items += 1
            elif status == "IN_PROGRESS":
                in_progress_items += 1

        completion_pct = int((completed_items / total_items * 100)) if total_items > 0 else 0

        # Determine overall state
        if total_items == 0:
            state = "CREATED"
        elif completed_items == total_items:
            state = "COMPLETED"
        elif blocked_items > 0:
            state = "AWAITING_INPUT"
        elif in_progress_items > 0:
            state = "IN_PROGRESS"
        else:
            state = "READY"

        # Update project status
        self.update_project_status(
            project_id,
            ProjectStatus(state) if state in ProjectStatus.__members__ else ProjectStatus.IN_PROGRESS,
            completion_percentage=completion_pct,
            blocked_items=blocked_items,
        )

        return {
            "project_id": project_id,
            "name": project.name,
            "state": state,
            "completion_percentage": completion_pct,
            "total_items": total_items,
            "completed_items": completed_items,
            "blocked_items": blocked_items,
            "in_progress_items": in_progress_items,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }
