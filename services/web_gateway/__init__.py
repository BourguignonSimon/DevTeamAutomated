"""Web Gateway service for project tracking and orchestrator interaction."""
from services.web_gateway.app import app, create_app

__all__ = ["app", "create_app"]
