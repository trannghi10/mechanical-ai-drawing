"""Carry the initiating actor into a worker without leaking between jobs."""
from functools import partial
from backend.services.account_service import ACTOR

_CURRENT = object()


def _run(actor, function, *args):
    token = ACTOR.set(dict(actor) if actor else None)
    try:
        return function(*args)
    finally:
        ACTOR.reset(token)


def submit(pool, function, *args, actor=_CURRENT):
    # Resumable jobs supply their persisted creator explicitly. Polling a job
    # must never transfer ownership to the person who reopened the page.
    if actor is _CURRENT:
        actor = ACTOR.get()
    return pool.submit(partial(_run, dict(actor) if actor else None, function), *args)
