#!/usr/bin/env python3
"""
Lab 5 - Part 1: Create a VM and install the flaskr application.

Portions adapted from Google's compute/api/create_instance.py sample
https://github.com/GoogleCloudPlatform/python-docs-samples (Apache 2.0 license).
"""
import os
import time

import google.auth
import googleapiclient.discovery

ZONE = "us-west1-a"
INSTANCE_NAME = "flask-part1"
MACHINE_TYPE = "e2-micro"        # use "e2-medium" while developing, switch back before submitting
IMAGE_PROJECT = "ubuntu-os-cloud"
IMAGE_FAMILY = "ubuntu-2204-lts"
FIREWALL_NAME = "allow-5000"
NETWORK_TAG = "allow-5000"

# Runs as root when the VM boots.
STARTUP_SCRIPT = """#!/bin/bash
mkdir -p /opt/flask && cd /opt/flask
apt-get update
apt-get install -y python3 python3-pip git
git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
cd flask-tutorial
python3 setup.py install
pip3 install -e .
export FLASK_APP=flaskr
flask init-db
nohup flask run -h 0.0.0.0 &
"""


def get_compute(credentials=None):
    """Build the Compute Engine client. Uses your default login unless credentials are passed in."""
    if credentials is None:
        credentials, _ = google.auth.default()
    return googleapiclient.discovery.build("compute", "v1", credentials=credentials)


def wait_for_operation(compute, project, operation, zone=None):
    """Poll a zonal (zone=...) or global (zone=None) operation until it finishes."""
    print(f"  waiting for {operation['name']} ...")
    while True:
        if zone:
            result = compute.zoneOperations().get(
                project=project, zone=zone, operation=operation["name"]).execute()
        else:
            result = compute.globalOperations().get(
                project=project, operation=operation["name"]).execute()
        if result["status"] == "DONE":
            if "error" in result:
                raise RuntimeError(result["error"])
            return result
        time.sleep(2)


def create_instance(compute, project, zone, name, startup_script,
                    source_image=None, extra_metadata=None):
    """Start creating a VM and return the operation. Used again in Parts 2 and 3."""
    if source_image is None:
        image = compute.images().getFromFamily(
            project=IMAGE_PROJECT, family=IMAGE_FAMILY).execute()
        source_image = image["selfLink"]

    metadata = [{"key": "startup-script", "value": startup_script}]
    metadata += extra_metadata or []

    config = {
        "name": name,
        "machineType": f"zones/{zone}/machineTypes/{MACHINE_TYPE}",
        "disks": [{
            "boot": True,
            "autoDelete": True,
            "initializeParams": {"sourceImage": source_image},
        }],
        "networkInterfaces": [{
            "network": "global/networks/default",
            "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
        }],
        "metadata": {"items": metadata},
    }
    return compute.instances().insert(project=project, zone=zone, body=config).execute()


def ensure_firewall_rule(compute, project):
    """Create the allow-5000 rule only if it doesn't already exist."""
    existing = compute.firewalls().list(
        project=project, filter=f'name = "{FIREWALL_NAME}"').execute()
    if existing.get("items"):
        print(f"Firewall rule {FIREWALL_NAME} already exists")
        return

    print(f"Creating firewall rule {FIREWALL_NAME}")
    body = {
        "name": FIREWALL_NAME,
        "network": "global/networks/default",
        "direction": "INGRESS",
        "sourceRanges": ["0.0.0.0/0"],
        "targetTags": [NETWORK_TAG],
        "allowed": [{"IPProtocol": "tcp", "ports": ["5000"]}],
    }
    op = compute.firewalls().insert(project=project, body=body).execute()
    wait_for_operation(compute, project, op)


def add_network_tag(compute, project, zone, name):
    """Apply the allow-5000 tag with setTags (the API needs the current fingerprint)."""
    inst = compute.instances().get(project=project, zone=zone, instance=name).execute()
    tags = inst.get("tags", {})
    items = tags.get("items", [])
    if NETWORK_TAG not in items:
        items.append(NETWORK_TAG)
    body = {"items": items, "fingerprint": tags["fingerprint"]}
    op = compute.instances().setTags(
        project=project, zone=zone, instance=name, body=body).execute()
    wait_for_operation(compute, project, op, zone=zone)


def get_external_ip(compute, project, zone, name):
    inst = compute.instances().get(project=project, zone=zone, instance=name).execute()
    return inst["networkInterfaces"][0]["accessConfigs"][0]["natIP"]


def run(compute, project, name=INSTANCE_NAME, zone=ZONE):
    """The whole Part 1 sequence. Part 3 calls this from inside VM-1."""
    print(f"Creating instance {name} in {zone}")
    op = create_instance(compute, project, zone, name, STARTUP_SCRIPT)
    wait_for_operation(compute, project, op, zone=zone)

    ensure_firewall_rule(compute, project)
    add_network_tag(compute, project, zone, name)

    ip = get_external_ip(compute, project, zone, name)
    print("\nThe Flask application is available at:\n")
    print(f"    http://{ip}:5000\n")
    print("(Give the startup script a few minutes to finish installing.)")


def get_project():
    _, project = google.auth.default()
    project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("No project found. Run: gcloud config set project YOUR_PROJECT_ID")
    return project


if __name__ == "__main__":
    run(get_compute(), get_project())
