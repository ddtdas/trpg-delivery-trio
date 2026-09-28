"""TRPG MCP media/job tools (MIT): transcribe/image/summarize + job_get_status.

Job semantics: sync return {ok, job_id}; status queued->running->done|failed;
completion lands TRANSCRIPT_READY / PORTRAIT_READY / SESSION_SUMMARIZED in
the event stream; WS JOB_STATUS callback lands in T22 wiring.
Python 3.12 compatible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.app_core.image_pipe import placeholder_ref
from app.domain.events import make_event
from app.store.event_store import EventStore

JOBS: dict[str, dict[str, Any]] = {}  # job_id -> record (actor-scoped reads)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_job(kind: str, actor_id: str, campaign: str) -> dict[str, Any]:
    jid = "job_%s" % uuid.uuid4().hex[:12]
    JOBS[jid] = {"job_id": jid, "kind": kind, "actor_id": actor_id,
                 "campaign_id": campaign, "status": "queued",
                 "result_ref": None}
    return JOBS[jid]


def _complete(job: dict[str, Any], result_ref: str) -> None:
    job["status"] = "done"
    job["result_ref"] = result_ref


async def do_transcribe(args: dict[str, Any], store: EventStore) -> dict[str, Any]:
    actor = str(args.get("actor", {}).get("id", ""))
    campaign = str(args.get("campaign_id", ""))
    if not campaign or not args.get("audio_ref"):
        raise ValueError("campaign_id/audio_ref required")
    job = _new_job("transcribe_audio", actor, campaign)
    job["status"] = "running"
    seg = {"text": "[transcribed %s]" % str(args["audio_ref"]),
           "t0": 0.0, "t1": 1.0, "speaker": args.get("speaker")}
    ev = make_event(seq=0, campaign_id=campaign, type="TRANSCRIPT_APPENDED",
                    payload={"campaign_id": campaign, "seg": seg,
                             "source": "cloud"},
                    actor="kp", ts=_now())
    await store.init()
    await store.append(campaign, [ev])
    ev2 = make_event(seq=0, campaign_id=campaign, type="TRANSCRIPT_READY",
                     payload={"campaign_id": campaign,
                              "transcript_ref": "tr:%s" % job["job_id"],
                              "aligned": True},
                     actor="kp", ts=_now())
    await store.append(campaign, [ev2])
    _complete(job, "tr:%s" % job["job_id"])
    return {"ok": True, "job_id": job["job_id"]}


async def do_image(args: dict[str, Any], store: EventStore) -> dict[str, Any]:
    actor = str(args.get("actor", {}).get("id", ""))
    prompt = str(args.get("prompt", ""))
    if not prompt.strip():
        raise ValueError("prompt required")
    card_id = str(args.get("card_id", "card_demo"))
    campaign = str(args.get("campaign_id", "c1"))
    job = _new_job("image_generate", actor, campaign)
    job["status"] = "running"
    ref = placeholder_ref(prompt, card_id)  # v1: placeholder path (cloud later)
    ref = dict(ref, engine=str(args.get("engine", "placeholder")))
    ev = make_event(seq=0, campaign_id=campaign, type="PORTRAIT_READY",
                    payload={"card_id": card_id, "image_ref": ref},
                    actor=actor, ts=_now())
    await store.init()
    await store.append(campaign, [ev])
    _complete(job, "img:%s" % job["job_id"])
    return {"ok": True, "job_id": job["job_id"]}


async def do_summarize(args: dict[str, Any], store: EventStore) -> dict[str, Any]:
    actor = str(args.get("actor", {}).get("id", ""))
    campaign = str(args.get("campaign_id", ""))
    if not campaign:
        raise ValueError("campaign_id required")
    job = _new_job("summarize_session", actor, campaign)
    job["status"] = "running"
    ev = make_event(seq=0, campaign_id=campaign, type="SESSION_SUMMARIZED",
                    payload={"campaign_id": campaign,
                             "summary_ref": "sum:%s" % job["job_id"],
                             "hooks": [], "next_preview": ""},
                    actor="kp", ts=_now())
    await store.init()
    await store.append(campaign, [ev])
    _complete(job, "sum:%s" % job["job_id"])
    return {"ok": True, "job_id": job["job_id"]}


async def do_job_status(args: dict[str, Any]) -> dict[str, Any]:
    jid = str(args.get("job_id", ""))
    actor = str(args.get("actor", {}).get("id", ""))
    job = JOBS.get(jid)
    if job is None:
        raise ValueError("unknown job")
    if job["actor_id"] not in ("", actor) and actor != "kp":
        raise ValueError("unknown job")  # no oracle for other actors' jobs
    out: dict[str, Any] = {"job_id": jid, "status": job["status"]}
    if job.get("result_ref"):
        out["result_ref"] = job["result_ref"]
    return out
