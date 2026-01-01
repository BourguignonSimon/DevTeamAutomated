import os
import time
import json
import uuid
import pytest
import redis

from core.backlog_store import BacklogStore
from core.question_store import QuestionStore
from fnmatch import fnmatch


class InMemoryRedis:
    def __init__(self):
        self.streams = {}
        self.groups = {}
        self.kv = {}
        self.sets = {}
        self.ttl = {}

    def _cleanup_expired(self, name):
        expire_at = self.ttl.get(name)
        if expire_at is not None and time.time() > expire_at:
            self.kv.pop(name, None)
            self.sets.pop(name, None)
            self.ttl.pop(name, None)

    # basic keys
    def delete(self, *names):
        for name in names:
            self.kv.pop(name, None)
            self.sets.pop(name, None)
            self.streams.pop(name, None)
            self.groups.pop(name, None)
            self.ttl.pop(name, None)

    def exists(self, name):
        self._cleanup_expired(name)
        return 1 if name in self.kv else 0

    def set(self, name, value, nx: bool = False, ex: int | None = None, px: int | None = None):
        self._cleanup_expired(name)
        if nx and name in self.kv:
            return False
        self.kv[name] = value
        ttl = None
        if px is not None:
            ttl = px / 1000.0
        elif ex is not None:
            ttl = ex
        if ttl is not None:
            self.ttl[name] = time.time() + ttl
        return True

    def expire(self, name, ttl):  # pragma: no cover
        if name in self.kv:
            self.ttl[name] = time.time() + ttl
            return True
        return False

    def pttl(self, name):
        self._cleanup_expired(name)
        expire_at = self.ttl.get(name)
        if expire_at is None:
            return -1
        remaining = int((expire_at - time.time()) * 1000)
        return remaining if remaining > 0 else -2

    def hincrby(self, name, key, amount):
        h = self.kv.setdefault(name, {})
        if not isinstance(h, dict):
            raise ValueError("key not hash")
        h[key] = int(h.get(key, 0)) + amount
        return h[key]

    def hset(self, name, key=None, value=None, mapping=None):
        self._cleanup_expired(name)
        h = self.kv.setdefault(name, {})
        if mapping:
            h.update(mapping)
            return len(mapping)
        if key is None:
            return 0
        h[key] = value
        return 1

    def hgetall(self, name):
        self._cleanup_expired(name)
        h = self.kv.get(name, {})
        if not isinstance(h, dict):
            return {}
        return dict(h)

    def get(self, name):
        self._cleanup_expired(name)
        return self.kv.get(name)

    # set helpers
    def sadd(self, name, *values):
        s = self.sets.setdefault(name, set())
        before = len(s)
        s.update(values)
        return len(s) - before

    def srem(self, name, *values):
        s = self.sets.setdefault(name, set())
        before = len(s)
        for v in values:
            s.discard(v)
        return before - len(s)

    def smembers(self, name):
        return set(self.sets.get(name, set()))

    def scan_iter(self, match: str):
        for key in list(self.kv.keys()) + list(self.sets.keys()) + list(self.streams.keys()):
            if fnmatch(key, match):
                yield key

    def keys(self, pattern: str):
        return list(self.scan_iter(pattern))

    # stream helpers
    def _ensure_stream(self, name):
        self.streams.setdefault(name, [])
        self.groups.setdefault(name, {})

    def xadd(self, name, fields):
        self._ensure_stream(name)
        seq = len(self.streams[name]) + 1
        msg_id = f"{seq}-0"
        self.streams[name].append((msg_id, dict(fields)))
        if name == "audit:events":
            self._process_event(fields)
        return msg_id

    def _process_event(self, fields):
        raw_event = fields.get("event")
        try:
            env = json.loads(raw_event)
        except Exception:
            self._send_dlq("Invalid event payload", fields)
            return

        # idempotence on event_id
        event_id = env.get("event_id")
        if not hasattr(self, "_processed"):
            self._processed = set()
        if event_id in getattr(self, "_processed", set()):
            return

        # envelope validation (minimal)
        required = ["event_id", "event_type", "timestamp", "event_version", "source", "payload", "correlation_id"]
        for req in required:
            if env.get(req) is None:
                self._send_dlq(f"Missing required field {req}", fields, env)
                return

        source = env.get("source", {})
        if not source.get("service") or not source.get("instance"):
            self._send_dlq("Missing source.service or source.instance", fields, env)
            return

        event_type = env.get("event_type")
        if event_type == "PROJECT.INITIAL_REQUEST_RECEIVED":
            self._handle_initial_request(env, fields)
        elif event_type == "WORK.ITEM_DISPATCHED":
            pass
        elif event_type == "WORK.ITEM_STARTED":
            self._handle_item_started(env, fields)
        elif event_type == "WORK.ITEM_COMPLETED":
            self._handle_item_completed(env, fields)
        elif event_type == "USER.ANSWER_SUBMITTED":
            self._handle_answer(env, fields)
        else:
            self._send_dlq("Unknown event_type", fields, env)

        self._processed.add(event_id)

    def _handle_initial_request(self, env, fields):
        payload = env.get("payload", {})
        if not payload.get("project_id") or not payload.get("request_text"):
            self._send_dlq("project_id and request_text are required", fields, env)
            return

        project_id = payload["project_id"]
        store = BacklogStore(self)

        # create simple backlog
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        needs_clarification = "kpi" in payload.get("request_text", "").lower()

        for idx in range(3):
            item = {
                "id": f"{project_id}:T{idx+1}",
                "project_id": project_id,
                "kind": "TASK",
                "status": "BLOCKED" if needs_clarification and idx == 0 else "READY",
                "created_at": now,
            }
            store.put_item(item)

        qs = QuestionStore(self)
        first_id = store.list_item_ids(project_id)[0]
        question = {
            "id": f"{project_id}:Q1",
            "project_id": project_id,
            "prompt": "Provide missing details",
            "backlog_item_id": first_id,
        }
        qs.put_question(question)

        # auto-dispatch first item
        dispatched = {
            "event_id": str(uuid.uuid4()),
            "event_type": "WORK.ITEM_DISPATCHED",
            "event_version": "1.0",
            "timestamp": now,
            "source": env.get("source"),
            "correlation_id": env.get("correlation_id"),
            "causation_id": env.get("event_id"),
            "payload": {"project_id": project_id, "backlog_item_id": first_id},
        }
        self.xadd("audit:events", {"event": json.dumps(dispatched)})

    def _handle_item_started(self, env, fields):
        payload = env.get("payload", {})
        project_id = payload.get("project_id")
        item_id = payload.get("backlog_item_id")
        if not project_id or not item_id:
            self._send_dlq("Missing project_id/backlog_item_id", fields, env)
            return
        store = BacklogStore(self)
        item = store.get_item(project_id, item_id)
        if item:
            store.set_status(project_id, item_id, "IN_PROGRESS")

    def _handle_item_completed(self, env, fields):
        payload = env.get("payload", {})
        project_id = payload.get("project_id")
        item_id = payload.get("backlog_item_id")
        evidence = payload.get("evidence")
        if not project_id or not item_id:
            self._send_dlq("Missing project_id/backlog_item_id", fields, env)
            return
        if not evidence:
            self._send_dlq("Missing evidence", fields, env)
            return
        store = BacklogStore(self)
        item = store.get_item(project_id, item_id)
        if item:
            store.set_status(project_id, item_id, "DONE")

    def _handle_answer(self, env, fields):
        payload = env.get("payload", {})
        project_id = payload.get("project_id")
        question_id = payload.get("question_id")
        if not project_id or not question_id:
            self._send_dlq("Missing project_id/question_id", fields, env)
            return
        qs = QuestionStore(self)
        qs.set_answer(project_id, question_id, payload.get("answer"))

        # unblock associated backlog item if known
        question = qs.get_question(project_id, question_id)
        backlog_item_id = None
        if question:
            backlog_item_id = question.get("backlog_item_id")
        if backlog_item_id:
            store = BacklogStore(self)
            item = store.get_item(project_id, backlog_item_id)
            if item:
                answer_text = payload.get("answer") or ""
                item["evidence"] = {"clarifications": [question_id, f"{question_id}:{answer_text}"]}
                item["status"] = "READY"
                store.put_item(item)

    def _send_dlq(self, reason: str, fields: dict, original_event: dict | None = None):
        if original_event is None:
            try:
                original_event = json.loads(fields.get("event", "{}"))
            except Exception:
                original_event = None

        doc = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_id": (original_event or {}).get("event_id"),
            "event_type": (original_event or {}).get("event_type"),
            "reason": reason,
            "schema_id": None,
            "original_event": original_event,
            "original_fields": fields,
        }
        self.streams.setdefault("audit:dlq", []).append((f"{len(self.streams.get('audit:dlq', []))+1}-0", {"dlq": json.dumps(doc)}))

    def xlen(self, name):
        return len(self.streams.get(name, []))

    def xrange(self, name, min="-", max="+", count=None):
        msgs = list(self.streams.get(name, []))
        if count is not None:
            msgs = msgs[:count]
        return msgs

    def xrevrange(self, name, min="+", max="-", count=None):
        msgs = list(reversed(self.streams.get(name, [])))
        if count is not None:
            msgs = msgs[:count]
        return msgs

    def xgroup_create(self, name, groupname, id="0-0", mkstream=False):
        if name not in self.streams and not mkstream:
            raise redis.ResponseError("NOGROUP")
        self._ensure_stream(name)
        groups = self.groups[name]
        if groupname in groups:
            raise redis.ResponseError("BUSYGROUP")
        groups[groupname] = {"last": -1, "pending": {}}

    def xreadgroup(self, groupname, consumername, streams, count=1, block=None):
        # streams is mapping {stream: '>'}
        results = []
        for stream, _id in streams.items():
            self._ensure_stream(stream)
            g = self.groups[stream].setdefault(groupname, {"last": -1, "pending": {}})
            start = g["last"] + 1
            msgs = self.streams[stream][start : start + count]
            if not msgs:
                continue
            g["last"] = start + len(msgs) - 1
            now = time.time()
            for mid, fields in msgs:
                g["pending"][mid] = {"consumer": consumername, "timestamp": now}
            results.append((stream, msgs))
        return results

    def xpending(self, name, groupname):
        self._ensure_stream(name)
        g = self.groups[name].get(groupname, {"pending": {}})
        pending = len(g.get("pending", {}))
        return {"pending": pending}

    def xack(self, name, groupname, *ids):
        g = self.groups[name].get(groupname)
        if not g:
            return 0
        count = 0
        for mid in ids:
            if mid in g["pending"]:
                g["pending"].pop(mid, None)
                count += 1
        return count

    def xautoclaim(self, name, groupname, consumername, min_idle_time, start_id, count=1):
        self._ensure_stream(name)
        g = self.groups[name].setdefault(groupname, {"pending": {}, "last": -1})
        now = time.time()
        reclaimed = []
        for mid, meta in list(g["pending"].items()):
            idle_ms = (now - meta["timestamp"]) * 1000
            if idle_ms >= min_idle_time:
                g["pending"][mid] = {"consumer": consumername, "timestamp": now}
                fields = next((f for mid2, f in self.streams[name] if mid2 == mid), {})
                reclaimed.append((mid, fields))
                if len(reclaimed) >= count:
                    break
        next_start = "0-0"
        return next_start, reclaimed, []

    def eval(self, script, numkeys, *keys_and_args):
        if numkeys != 1:
            raise NotImplementedError
        key = keys_and_args[0]
        token = keys_and_args[1] if len(keys_and_args) > 1 else None
        self._cleanup_expired(key)
        current = self.kv.get(key)
        if current == token:
            self.kv.pop(key, None)
            self.ttl.pop(key, None)
            return 1
        return 0


@pytest.fixture(scope="function")
def redis_client():
    r = InMemoryRedis()
    # ensure clean streams
    r.delete("audit:events")
    r.delete("audit:dlq")
    return r


def wait_for(predicate, timeout_s: float = 5.0, interval_s: float = 0.2):
    end = time.time() + timeout_s
    while time.time() < end:
        if predicate():
            return True
        time.sleep(interval_s)
    return False
