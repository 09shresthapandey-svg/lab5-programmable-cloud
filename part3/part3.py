#!/usr/bin/env python3
"""
Lab 5 - Part 3: Create VM-1 using an explicit service account.
VM-1 then runs vm1-launch-vm2-code.py, which creates VM-2 running the Flask app.

Run from Cloud Shell with service-credentials.json in this (part3) directory.
"""
import os
import sys

import googleapiclient.discovery
import google.oauth2.service_account as service_account

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "part1"))
import part1  # noqa: E402  reuse create_instance, wait_for_operation, STARTUP_SCRIPT

#
# Use Google Service Account - see
# https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html
#
CRED_FILE = os.path.join(HERE, "service-credentials.json")
credentials = service_account.Credentials.from_service_account_file(filename=CRED_FILE)
project = os.getenv("GOOGLE_CLOUD_PROJECT") or credentials.project_id
service = googleapiclient.discovery.build("compute", "v1", credentials=credentials)

ZONE = "us-west1-a"
VM1_NAME = "vm1-launcher"

# Startup script for VM-1: fetch everything from metadata, install libraries,
# then run the program that launches VM-2.
VM1_STARTUP_SCRIPT = """#!/bin/bash
mkdir -p /srv
cd /srv
MD=http://metadata/computeMetadata/v1/instance/attributes
curl -s $MD/vm2-startup-script  -H "Metadata-Flavor: Google" > vm2-startup-script.sh
curl -s $MD/service-credentials -H "Metadata-Flavor: Google" > service-credentials.json
curl -s $MD/vm1-launch-vm2-code -H "Metadata-Flavor: Google" > vm1-launch-vm2-code.py
export GOOGLE_CLOUD_PROJECT=$(curl -s $MD/project -H "Metadata-Flavor: Google")

apt-get update
apt-get install -y python3-pip
pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
python3 ./vm1-launch-vm2-code.py
"""


def read(name):
    with open(os.path.join(HERE, name)) as f:
        return f.read()


def main():
    extra_metadata = [
        {"key": "vm2-startup-script",  "value": part1.STARTUP_SCRIPT},   # Flask installer for VM-2
        {"key": "service-credentials", "value": read("service-credentials.json")},
        {"key": "vm1-launch-vm2-code", "value": read("vm1-launch-vm2-code.py")},
        {"key": "project",             "value": project},
    ]

    print(f"Creating {VM1_NAME} in project {project}")
    op = part1.create_instance(service, project, ZONE, VM1_NAME,
                               VM1_STARTUP_SCRIPT, extra_metadata=extra_metadata)
    part1.wait_for_operation(service, project, op, zone=ZONE)

    print(f"\n{VM1_NAME} is running. In ~5-10 minutes it will create 'vm2-flask'.")
    print("Watch VM-1's progress (the Flask URL is printed at the end) with:")
    print(f"  gcloud compute instances get-serial-port-output {VM1_NAME} --zone {ZONE} | tail -40")


if __name__ == "__main__":
    main()
