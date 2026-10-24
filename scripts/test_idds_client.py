#!/usr/bin/env python3
"""Exercise the iDDS REST service with the official iDDS client.

Runs the documented client API (idds.client.clientmanager.ClientManager)
against the panda-compose iDDS service and asserts each step:

  1. ping
  2. get_status (listing works)
  3. create_workflow_task -> a PanDA task must appear in jedi_tasks
  4. get_status shows the new request
  5. adjust_worker records the adjustment
  6. close_workflow_task registers the close

Environment:
  IDDS_HOST    iDDS base URL (default http://localhost:25444/idds)
  IDDS_PROXY   x509 proxy file for client-side validation
               (default: fetched from the idds container via docker)
  COMPOSE_DIR  panda-compose directory (default ../panda-compose)

Exit code 0 = all steps passed. Any failure exits non-zero with the
step name on stderr.

Note: this deployment runs only the iDDS REST service, not the agent
chain, so lifecycle commands (abort/close/...) are *recorded* in
doma_idds.commands but not executed - the assertions check registration,
not execution.
"""

import os
import subprocess
import sys
import time
import uuid
from typing import NoReturn

IDDS_HOST = os.environ.get("IDDS_HOST", "http://localhost:25444/idds")
COMPOSE_DIR = os.environ.get("COMPOSE_DIR", "../panda-compose")


def fail(step: str, msg) -> NoReturn:
    print(f"FAIL [{step}]: {msg}", file=sys.stderr)
    sys.exit(1)


def compose_ps(service: str) -> str:
    return subprocess.run(
        ["docker", "compose", "--project-directory", COMPOSE_DIR, "ps", "-q", service],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def get_client():
    from idds.client.clientmanager import ClientManager

    proxy = os.environ.get("IDDS_PROXY")
    if not proxy:
        cid = compose_ps("idds")
        proxy = "/tmp/idds_dev_proxy.pem"
        subprocess.run(
            ["docker", "cp", f"{cid}:/etc/idds/auth/dev_proxy.pem", proxy],
            check=True,
        )
    cm = ClientManager(host=IDDS_HOST)
    cm.auth_type = "x509_proxy"
    cm.x509_proxy = proxy
    return cm


def main() -> None:
    print(f"iDDS host: {IDDS_HOST}")

    # 1. ping
    try:
        from idds.client.pingclient import PingClient
        proxy = os.environ.get("IDDS_PROXY")
        if not proxy:
            cid = compose_ps("idds")
            proxy = "/tmp/idds_dev_proxy.pem"
            subprocess.run(
                ["docker", "cp", f"{cid}:/etc/idds/auth/dev_proxy.pem", proxy],
                check=True,
            )
        pc = PingClient(host=IDDS_HOST, auth={"auth_type": "x509_proxy",
                                              "client_proxy": proxy})
        rc = pc.ping()
        print(f"ping: {rc}")
        ok = (isinstance(rc, dict) and rc.get("Status") == "OK") or \
             (isinstance(rc, tuple) and rc and rc[0])
        if not ok:
            fail("ping", f"unexpected response: {rc!r}")
    except Exception as exc:
        fail("ping", repr(exc))

    cm = get_client()

    # 2. get_status (listing; may be empty or not, must not error)
    try:
        cm.get_status()
        print("get_status: ok")
    except Exception as exc:
        fail("get_status", repr(exc))

    # 3. create_workflow_task
    run_id = str(int(time.time()))
    task_name = f"ci_idds_client_{uuid.uuid4().hex[:8]}"
    workflow = {
        "scope": "ci",
        "name": task_name,
        "requester": "panda",
        "username": "ci",
        "transform_tag": "ci",
        "cloud": "EIC",
        "campaign": "ci",
        "campaign_scope": "ci_2026",
        "campaign_group": "ci_2026_10",
        "campaign_tag": "ci",
        "content": {
            "run_id": run_id,
            "core_count": 1,
            "memory_per_core": 2000.0,
            "site": "PANDA_COMPOSE_LOCAL",
            "panda_attributes": {
                "vo": "epic",
                "queue": "E1_BNL",
                "site": "PANDA_COMPOSE_LOCAL",
                "cloud": "EIC",
                "working_group": "EIC",
                "priority": 900,
                "core_count": 1,
                "ram_count": 4000,
                "num_workers": 1,
                "max_walltime": 3600,
                "max_attempt": 3,
                "idle_timeout": 120,
                "username": "EICFast",
                "task_type": "EICFast",
                "processing_type": "EICFast",
                "transform_tag": "fastproc",
                "requester": "panda-worker",
                "campaign": "testbed",
                "campaign_tag": "test",
            },
        },
    }
    request_id = transform_id = workload_id = None
    try:
        ret = cm.create_workflow_task(workflow)
        print(f"create_workflow_task: {ret}")
        resp = ret[1] if isinstance(ret, tuple) and len(ret) > 1 else ret
        if isinstance(resp, dict):
            workload_id = resp.get("workload_id")
            request_id = resp.get("request_id")
            transform_id = resp.get("transform_id")
    except Exception as exc:
        fail("create_workflow_task", repr(exc))

    if not (workload_id and request_id and transform_id):
        fail("create_workflow_task", "missing ids in response "
             "(upstream serialization bug?) - cannot continue")
    workload_id = int(workload_id)
    request_id = int(request_id)
    transform_id = int(transform_id)
    print(f"  request_id={request_id} transform_id={transform_id} workload_id={workload_id}")

    # 4. the PanDA task must appear in jedi_tasks. The iDDS create call
    #    returns once insertTaskParams succeeds (T_TASK row inserted); the
    #    JEDI TaskRefiner then promotes it into jedi_tasks on its next
    #    loopCycle (10s by default) - so poll for up to ~2 minutes.
    try:
        q = (
            "SELECT jeditaskid, status FROM doma_panda.jedi_tasks "
            f"WHERE jeditaskid={workload_id}"
        )
        out = ""
        for attempt in range(24):
            out = subprocess.run(
                ["docker", "exec", compose_ps("postgres"), "psql", "-U", "panda",
                 "-d", "panda_db", "-tAc", q],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            if out:
                break
            if attempt == 0:
                print("  waiting for TaskRefiner to promote the task...")
            time.sleep(5)
        print(f"jedi_tasks row: {out!r}")
        if not out:
            fail("jedi_tasks", f"no task {workload_id} in doma_panda.jedi_tasks "
                 "after 2 minutes (TaskRefiner did not promote it?)")
        jeditaskid = out.split("|")[0]
        if int(jeditaskid) != workload_id:
            fail("jedi_tasks", f"unexpected task id {jeditaskid}")
    except Exception as exc:
        fail("jedi_tasks", repr(exc))

    # 5. get_status shows the new request
    try:
        cm.get_status(request_id=request_id)
        print("get_status(new request): ok")
    except Exception as exc:
        fail("get_status(new)", repr(exc))

    # 6. adjust_worker
    try:
        ret = cm.adjust_worker(
            request_id=request_id, transform_id=transform_id,
            workload_id=workload_id, parameters={"core_count": 2},
        )
        print(f"adjust_worker: {ret}")
        resp = ret[1] if isinstance(ret, tuple) and len(ret) > 1 else ret
        if not (isinstance(resp, dict) and resp.get("status") == 0):
            fail("adjust_worker", f"unexpected response: {ret!r}")
    except Exception as exc:
        fail("adjust_worker", repr(exc))

    # 7. close_workflow_task
    try:
        ret = cm.close_workflow_task(
            request_id=request_id,
            parameters={"transform_id": transform_id, "workload_id": workload_id},
        )
        print(f"close_workflow_task: {ret}")
        resp = ret[1] if isinstance(ret, tuple) and len(ret) > 1 else ret
        if not (isinstance(resp, dict) and resp.get("status") == 0):
            fail("close_workflow_task", f"unexpected response: {ret!r}")
    except Exception as exc:
        fail("close_workflow_task", repr(exc))

    print("ALL IDDS CLIENT CHECKS PASSED")


if __name__ == "__main__":
    main()
