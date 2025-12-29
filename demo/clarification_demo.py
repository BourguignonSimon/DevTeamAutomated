import json
import os
import sys
import uuid
from datetime import datetime

from core.config import Settings
from core.event_utils import envelope
from core.question_store import QuestionStore
from core.redis_streams import build_redis_client


def main() -> int:
    """Interactive helper for EPIC 3.

    1) Lists open questions for a project
    2) Lets the user submit an answer (USER.ANSWER_SUBMITTED)
    """
    s = Settings()
    r = build_redis_client(s.redis_host, s.redis_port, s.redis_db)
    qs = QuestionStore(r)

    project_id = input("project_id > ").strip()
    open_ids = qs.list_open(project_id)
    if not open_ids:
        print("No open questions.")
        return 0

    print("Open questions:")
    for i, qid in enumerate(open_ids, start=1):
        q = qs.get_question(project_id, qid)
        if not q:
            continue
        print(f"{i}) {qid} | backlog_item_id={q['backlog_item_id']} | expected={q['expected_format']}\n   {q['text']}")

    pick = input("Choose question number > ").strip()
    try:
        idx = int(pick) - 1
        qid = open_ids[idx]
    except Exception:
        print("Invalid selection")
        return 1

    q = qs.get_question(project_id, qid)
    if not q:
        print("Question not found")
        return 1

    raw_answer = input("answer > ").strip()
    # For json expected_format, allow raw json string (or simple text)
    answer: object
    if q["expected_format"] == "number":
        answer = raw_answer
    elif q["expected_format"] == "json":
        answer = raw_answer
    else:
        answer = raw_answer

    corr = str(uuid.uuid4())
    env = envelope(
        event_type="USER.ANSWER_SUBMITTED",
        payload={"project_id": project_id, "question_id": qid, "answer": answer},
        source="demo_user",
        correlation_id=corr,
        causation_id=None,
    )
    r.xadd(s.stream_name, {"event": json.dumps(env)})
    print("Submitted USER.ANSWER_SUBMITTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
