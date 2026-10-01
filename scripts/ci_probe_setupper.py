#!/usr/bin/env python3
"""CI diagnostic probe for the JEDI defined->activated stall.

Run INSIDE the panda-server container (which has the pandaserver package):
    /opt/panda/bin/python /tmp/ci_probe_setupper.py <PandaID> [<PandaID> ...]

For the given jobs it:
  1. prints their current state (jobStatus, dispatchDBlock, prodDBlock, destSE, VO)
  2. calls Client.reassign_jobs (the exact trigger JEDI uses) and reprints status
  3. runs the server-side Setupper directly and reprints status
so we can see whether activation is blocked at the reassign trigger or in the
Setupper itself (activated vs assigned vs unchanged). Diagnostic only; it does
not change workflow behavior.
"""
import sys
import time
import traceback

ids = []
for a in sys.argv[1:]:
    a = a.strip().strip(",")
    if a:
        ids.append(int(a))
if not ids:
    print("no PandaIDs given")
    sys.exit(0)

from pandaserver.config import panda_config
from pandaserver.taskbuffer.TaskBuffer import taskBuffer

taskBuffer.init(panda_config.dbhost, panda_config.dbpasswd, nDBConnection=1)


def status(pid):
    for tbl in ("defined", "active", "archived"):
        js = taskBuffer.peekJobs(
            [pid],
            fromDefined=(tbl == "defined"),
            fromActive=(tbl == "active"),
            fromArchived=(tbl == "archived"),
            fromWaiting=False,
        )
        if js and js[0] is not None and js[0].jobStatus != "unknown":
            return f"{tbl}:{js[0].jobStatus}"
    return "not-found"


print("=== initial peek ===", flush=True)
jobs = []
for pid in ids:
    js = taskBuffer.peekJobs([pid], fromDefined=True, fromActive=False, fromArchived=False, fromWaiting=False)
    j = js[0] if js else None
    if j is None or j.jobStatus == "unknown":
        print(f"peek {pid} -> not in jobsDefined4")
        continue
    print(
        f"peek {pid} -> {j.jobStatus} "
        f"dispatchDBlock={j.dispatchDBlock!r} prodDBlock={j.prodDBlock!r} "
        f"destSE={j.destinationSE!r} VO={j.VO!r} prodSourceLabel={j.prodSourceLabel!r}"
    )
    jobs.append(j)

print("=== calling Client.reassign_jobs (JEDI's trigger) ===", flush=True)
try:
    from pandaserver.userinterface import Client

    print("reassign_jobs ->", Client.reassign_jobs(ids))
except Exception as exc:
    print("reassign_jobs EXC:", exc)
    traceback.print_exc()
time.sleep(5)
for pid in ids:
    print(f"after reassign {pid} -> {status(pid)}")

print("=== running Setupper directly ===", flush=True)
try:
    from pandaserver.dataservice.setupper import Setupper

    Setupper(taskBuffer, jobs, resubmit=True, first_submission=True).run()
except Exception as exc:
    print("Setupper EXC:", exc)
    traceback.print_exc()
for pid in ids:
    print(f"after Setupper {pid} -> {status(pid)}")

print("=== actual update_jobs source in THIS image ===", flush=True)
try:
    import inspect
    from pandaserver.dataservice import setupper as _su

    for name in ("update_jobs", "run"):
        fn = getattr(_su.Setupper, name, None)
        if fn is not None:
            print(f"--- Setupper.{name} ---")
            print(inspect.getsource(fn))
except Exception as exc:
    print("source dump EXC:", exc)
    traceback.print_exc()

print("=== DBProxy.activateJob source in THIS image ===", flush=True)
try:
    import inspect

    proxy = taskBuffer.proxyPool.getProxy()
    try:
        print(inspect.getsource(proxy.activateJob))
    finally:
        taskBuffer.proxyPool.putProxy(proxy)
except Exception as exc:
    print("activateJob source EXC:", exc)
    traceback.print_exc()

print("=== calling taskBuffer.activateJobs directly (fresh peek) ===", flush=True)
try:
    fresh = []
    for pid in ids:
        js = taskBuffer.peekJobs([pid], fromDefined=True, fromActive=False, fromArchived=False, fromWaiting=False)
        if js and js[0] is not None and js[0].jobStatus != "unknown":
            fresh.append(js[0])
    print(f"activateJobs on {len(fresh)} jobs -> {taskBuffer.activateJobs(fresh)}")
except Exception as exc:
    print("activateJobs EXC:", exc)
    traceback.print_exc()
for pid in ids:
    print(f"after activateJobs {pid} -> {status(pid)}")
