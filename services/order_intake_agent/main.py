from __future__ import annotations

import threading

import uvicorn

from core.redis_streams import build_redis_client
from core.logging import setup_logging
from services.order_intake_agent.app import create_app
from services.order_intake_agent.processor import OrderIntakeAgent
from services.order_intake_agent.settings import OrderIntakeSettings


def main() -> None:  # pragma: no cover
    settings = OrderIntakeSettings()
    setup_logging(settings.log_level)
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)
    agent = OrderIntakeAgent(r, settings)
    t = threading.Thread(target=agent.run, daemon=True)
    t.start()
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
