from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

import redis


class QuestionStore:
    """Redis-backed store for Questions.

    NOTE: The Question object schema (objects/question.v1) has `additionalProperties=false`.
    To keep the object contract strict, we store answers and status in separate keys.

    Storage:
      - question doc:  audit:project:{project_id}:question:{question_id}
      - index all:     audit:project:{project_id}:questions:index
      - index open:    audit:project:{project_id}:questions:open
      - answer:        audit:question:{question_id}:answer
    """

    def __init__(self, r: redis.Redis, prefix: str = "audit"):
        self.r = r
        self.prefix = prefix

    def _qkey(self, project_id: str, question_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:question:{question_id}"

    def _index(self, project_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:questions:index"

    def _open(self, project_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:questions:open"

    def _answer_key(self, question_id: str) -> str:
        return f"{self.prefix}:question:{question_id}:answer"

    @staticmethod
    def _decode(v) -> str:
        if isinstance(v, bytes):
            return v.decode("utf-8")
        return str(v)

    def create_question(
        self,
        *,
        project_id: str,
        backlog_item_id: str,
        question_text: str,
        answer_type: str,
        status: str = "OPEN",
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        qid = str(uuid.uuid4())
        q = {
            "id": qid,
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "question_text": question_text,
            "answer_type": answer_type,
            "status": status,
            "correlation_id": correlation_id,
        }
        self.put_question(q)
        return q

    def put_question(self, q: Dict[str, Any]) -> None:
        project_id = q["project_id"]
        qid = q["id"]
        self.r.set(self._qkey(project_id, qid), json.dumps(q))
        self.r.sadd(self._index(project_id), qid)
        self.r.sadd(self._open(project_id), qid)

    def get_question(self, project_id: str, question_id: str) -> Optional[Dict[str, Any]]:
        raw = self.r.get(self._qkey(project_id, question_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def list_open(self, project_id: str) -> List[str]:
        return sorted([self._decode(x) for x in self.r.smembers(self._open(project_id))])

    def list_all(self, project_id: str) -> List[str]:
        return sorted([self._decode(x) for x in self.r.smembers(self._index(project_id))])

    def set_answer(self, project_id: str, question_id: str, normalized_answer: Any) -> None:
        # store as json for non-strings
        self.r.set(self._answer_key(question_id), json.dumps(normalized_answer))
        # mark closed
        self.r.srem(self._open(project_id), question_id)

    def get_answer(self, question_id: str) -> Optional[Any]:
        raw = self.r.get(self._answer_key(question_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def close_question(self, project_id: str, question_id: str) -> None:
        q = self.get_question(project_id, question_id)
        if not q:
            return
        if q.get("status") != "CLOSED":
            q["status"] = "CLOSED"
            self.r.set(self._qkey(project_id, question_id), json.dumps(q))
        self.r.srem(self._open(project_id), question_id)
