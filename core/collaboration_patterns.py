from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from core.agent_team import SharedContext, TeamMember, TeamTask


def sequential_pipeline(
    members: List["TeamMember"],
    tasks: List["TeamTask"],
    shared_context: "SharedContext",
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for index, task in enumerate(tasks):
        member = members[index % len(members)]
        output = member.execute(task, shared_context)
        results.append({"task": task.name, "agent": member.name, "output": output})
        shared_context.store_result(f"{task.name}:{member.name}", output)
    return results


def parallel_fusion(
    members: List["TeamMember"],
    tasks: List["TeamTask"],
    shared_context: "SharedContext",
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for index, task in enumerate(tasks):
        member = members[index % len(members)]
        output = member.execute(task, shared_context)
        results.append({"task": task.name, "agent": member.name, "output": output})
    shared_context.add_decision({"pattern": "parallel_fusion", "tasks": len(tasks)})
    return results


def hierarchical_flow(
    leader: "TeamMember",
    members: List["TeamMember"],
    tasks: List["TeamTask"],
    shared_context: "SharedContext",
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for task in tasks:
        output = leader.execute(task, shared_context)
        results.append({"task": task.name, "agent": leader.name, "output": output})
    shared_context.add_decision({"pattern": "hierarchical", "leader": leader.name})
    return results


def iterative_feedback(
    members: List["TeamMember"],
    tasks: List["TeamTask"],
    shared_context: "SharedContext",
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for task in tasks:
        first = members[0].execute(task, shared_context)
        from core.agent_team import TeamTask

        refined_task = TeamTask(
            name=f"{task.name}-refined",
            description=f"Refinement of {task.description}",
            payload={"initial": first, **task.payload},
        )
        second = members[1 % len(members)].execute(refined_task, shared_context)
        results.append({"task": task.name, "agent": members[0].name, "output": first})
        results.append({"task": refined_task.name, "agent": members[1 % len(members)].name, "output": second})
    shared_context.add_decision({"pattern": "iterative_feedback", "iterations": len(tasks)})
    return results
