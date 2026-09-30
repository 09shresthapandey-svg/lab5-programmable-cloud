#!/usr/bin/env python3
"""
Lab 5 - Part 2: Snapshot the Part 1 VM, make an image, create 3 timed clones.
Run this only after the Part 1 app is working in your browser.
"""
import os
import sys
import time

from googleapiclient.errors import HttpError

# Reuse the helpers from Part 1
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "part1"))
import part1  # noqa: E402

ZONE = part1.ZONE
SOURCE_INSTANCE = part1.INSTANCE_NAME               # "flask-part1"
SNAPSHOT_NAME = f"base-snapshot-{SOURCE_INSTANCE}"  # required naming: base-snapshot-<instance>
IMAGE_NAME = f"image-{SOURCE_INSTANCE}"
CLONES = ["flask-clone-1", "flask-clone-2", "flask-clone-3"]

# flaskr is already installed on the image; it just needs to be started at boot.
RUN_SCRIPT = """#!/bin/bash
cd /opt/flask/flask-tutorial
export FLASK_APP=flaskr
nohup flask run -h 0.0.0.0 &
"""


def exists(request):
    try:
        request.execute()
        return True
    except HttpError as e:
        if e.resp.status == 404:
            return False
        raise


def main():
    compute = part1.get_compute()
    project = part1.get_project()

    # 1. Find the boot disk of the Part 1 instance (don't assume its name)
    inst = compute.instances().get(project=project, zone=ZONE, instance=SOURCE_INSTANCE).execute()
    boot_disk = next(d for d in inst["disks"] if d.get("boot"))
    disk_name = boot_disk["source"].split("/")[-1]
    print(f"Boot disk of {SOURCE_INSTANCE}: {disk_name}")

    # 2. Snapshot it with disks.createSnapshot
    if exists(compute.snapshots().get(project=project, snapshot=SNAPSHOT_NAME)):
        print(f"Snapshot {SNAPSHOT_NAME} already exists")
    else:
        print(f"Creating snapshot {SNAPSHOT_NAME}")
        op = compute.disks().createSnapshot(
            project=project, zone=ZONE, disk=disk_name, body={"name": SNAPSHOT_NAME}).execute()
        part1.wait_for_operation(compute, project, op, zone=ZONE)

    # 3. Build a custom image from the snapshot
    if exists(compute.images().get(project=project, image=IMAGE_NAME)):
        print(f"Image {IMAGE_NAME} already exists")
    else:
        print(f"Creating image {IMAGE_NAME}")
        op = compute.images().insert(project=project, body={
            "name": IMAGE_NAME,
            "sourceSnapshot": f"global/snapshots/{SNAPSHOT_NAME}",
        }).execute()
        part1.wait_for_operation(compute, project, op)
    source_image = f"projects/{project}/global/images/{IMAGE_NAME}"

    # 4. Create three instances from the image, timing each one
    part1.ensure_firewall_rule(compute, project)
    results = []
    for name in CLONES:
        print(f"Creating {name}")
        start = time.time()
        op = part1.create_instance(compute, project, ZONE, name, RUN_SCRIPT,
                                   source_image=source_image)
        part1.wait_for_operation(compute, project, op, zone=ZONE)
        elapsed = time.time() - start

        part1.add_network_tag(compute, project, ZONE, name)   # not part of the timing
        ip = part1.get_external_ip(compute, project, ZONE, name)
        print(f"  {name} took {elapsed:.2f} s -> http://{ip}:5000")
        results.append((name, elapsed))

    # 5. Write TIMING.md
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TIMING.md")
    with open(path, "w") as f:
        f.write("# Instance creation times (from image of snapshot "
                f"`{SNAPSHOT_NAME}`)\n\n")
        f.write("| Instance | Seconds |\n|---|---|\n")
        for name, t in results:
            f.write(f"| {name} | {t:.2f} |\n")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
