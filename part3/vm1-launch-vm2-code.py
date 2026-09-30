#!/usr/bin/env python3
"""
Runs ON VM-1 (in /srv). Uses the explicit service account credentials to
create VM-2 running the Flask app -- the same steps as Part 1.
Portions adapted from Google's compute/api/create_instance.py sample (Apache 2.0).
"""
import os
import time

import googleapiclient.discovery
import google.oauth2.service_account as service_account

credentials = service_account.Credentials.from_service_account_file(filename="service-credentials.json")
project = os.getenv("GOOGLE_CLOUD_PROJECT") or credentials.project_id
service = googleapiclient.discovery.build("compute", "v1", credentials=credentials)

ZONE = "us-west1-a"
VM2_NAME = "vm2-flask"
TAG = "allow-5000"

with open("vm2-startup-script.sh") as f:
    VM2_STARTUP_SCRIPT = f.read()


def wait(op, zone=None):
    while True:
        if zone:
            r = service.zoneOperations().get(project=project, zone=zone, operation=op["name"]).execute()
        else:
            r = service.globalOperations().get(project=project, operation=op["name"]).execute()
        if r["status"] == "DONE":
            if "error" in r:
                raise RuntimeError(r["error"])
            return r
        time.sleep(2)


# 1. Create VM-2 (note: no credentials are passed to VM-2)
image = service.images().getFromFamily(project="ubuntu-os-cloud", family="ubuntu-2204-lts").execute()
config = {
    "name": VM2_NAME,
    "machineType": f"zones/{ZONE}/machineTypes/e2-micro",
    "disks": [{"boot": True, "autoDelete": True,
               "initializeParams": {"sourceImage": image["selfLink"]}}],
    "networkInterfaces": [{"network": "global/networks/default",
                           "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}]}],
    "metadata": {"items": [{"key": "startup-script", "value": VM2_STARTUP_SCRIPT}]},
}
print(f"Creating {VM2_NAME}")
wait(service.instances().insert(project=project, zone=ZONE, body=config).execute(), zone=ZONE)

# 2. Firewall rule, only if missing
rules = service.firewalls().list(project=project, filter=f'name = "{TAG}"').execute()
if not rules.get("items"):
    body = {"name": TAG, "network": "global/networks/default", "direction": "INGRESS",
            "sourceRanges": ["0.0.0.0/0"], "targetTags": [TAG],
            "allowed": [{"IPProtocol": "tcp", "ports": ["5000"]}]}
    wait(service.firewalls().insert(project=project, body=body).execute())

# 3. setTags
inst = service.instances().get(project=project, zone=ZONE, instance=VM2_NAME).execute()
body = {"items": [TAG], "fingerprint": inst["tags"]["fingerprint"]}
wait(service.instances().setTags(project=project, zone=ZONE, instance=VM2_NAME, body=body).execute(), zone=ZONE)

# 4. Print the URL
inst = service.instances().get(project=project, zone=ZONE, instance=VM2_NAME).execute()
ip = inst["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
print(f"VM-2 Flask application is available at: http://{ip}:5000")
