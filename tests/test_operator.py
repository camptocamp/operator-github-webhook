import datetime
import json
import logging
import os.path
import subprocess
import time

import pytest
import requests
import yaml

LOG = logging.getLogger(__name__)


@pytest.fixture
def install_operator(scope="session"):
    # Create the operator
    LOG.warning("Create operator: %s", datetime.datetime.now())
    with open("operator.yaml", "w") as operator_file:
        subprocess.run(
            [
                "helm",
                "template",
                "test",
                ".",
                "--namespace=default",
                f"--set=image.tag=latest,env.GITHUB_TOKEN={os.environ['GITHUB_TOKEN']},env.LOG_LEVEL=DEBUG",
            ],
            stdout=operator_file,
            check=True,
        )
    subprocess.run(["kubectl", "apply", "-f", "operator.yaml"], check=True)

    pods = []
    success = False
    for _ in range(100):
        pods = json.loads(
            subprocess.run(
                ["kubectl", "get", "pods", "--output=json"], check=True, stdout=subprocess.PIPE
            ).stdout
        )
        if (
            len(pods["items"]) == 1
            and len([c for c in pods["items"][0]["status"]["conditions"] if c["status"] != "True"]) == 0
        ):
            success = True
            break
        time.sleep(1)
    assert success, "The operator didn't run correctly: \n" + yaml.dump(pods)
    LOG.warning("Operator created: %s", datetime.datetime.now())

    yield
    # We should have the pod to be able to extract the logs
    # subprocess.run(["kubectl", "delete", "-f", "operator.yaml"], check=True)
    os.remove("operator.yaml")


AUTH_HEADER = "Bearer {}".format(
    os.environ["GITHUB_TOKEN"]
    if "GITHUB_TOKEN" in os.environ
    else subprocess.check_output(["gopass", "gs/ci/github/token/gopass"]).strip().decode()
)


def test_operator(install_operator):

    # Initialise the source and the config
    subprocess.run(["kubectl", "delete", "-f", "tests/webhook.yaml"])
    subprocess.run(["kubectl", "delete", "-f", "tests/webhook-duplicate.yaml"])

    # Clean the olf webhook
    webhooks = requests.get(
        "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
        headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
    )
    webhooks.raise_for_status()
    for webhook in webhooks.json():
        if webhook["config"]["url"] == "https://example.com":
            requests.delete(
                f"https://api.github.com/repos/camptocamp/operator-github-webhook/hooks/{webhook['id']}",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": AUTH_HEADER,
                },
            )

    for _ in range(10):
        webhooks = [
            wh
            for wh in requests.get(
                "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
                headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
            ).json()
            if wh["config"]["url"] == "https://example.com"
        ]
        if len(webhooks) == 0:
            break
        else:
            time.sleep(1)
    assert len(webhooks) == 0

    # Test creation
    LOG.warning("Test creation: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "apply", "-f", "tests/webhook.yaml"], check=True)
    for _ in range(10):
        webhooks = [
            wh
            for wh in requests.get(
                "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
                headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
            ).json()
            if wh["config"]["url"] == "https://example.com"
        ]
        if len(webhooks) == 1:
            break
        else:
            time.sleep(1)
    assert len(webhooks) == 1

    # Test duplicate
    LOG.warning("Test duplicate: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "apply", "-f", "tests/webhook-duplicate.yaml"], check=True)
    time.sleep(4)
    webhooks = [
        wh
        for wh in requests.get(
            "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
        ).json()
        if wh["config"]["url"] == "https://example.com"
    ]
    assert len(webhooks) == 1

    # Test remove duplicate
    LOG.warning("Test remove duplicate: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "delete", "-f", "tests/webhook-duplicate.yaml"], check=True)
    time.sleep(4)
    webhooks = [
        wh
        for wh in requests.get(
            "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
        ).json()
        if wh["config"]["url"] == "https://example.com"
    ]
    assert len(webhooks) == 1

    # Test modification
    LOG.warning("Test modification: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "apply", "-f", "tests/webhook-form.yaml"], check=True)

    time.sleep(4)
    webhooks = [
        wh
        for wh in requests.get(
            "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
        ).json()
        if wh["config"]["url"] == "https://example.com"
    ]
    assert len(webhooks) == 1

    # Test remove
    LOG.warning("Test remove: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "delete", "-f", "tests/webhook-form.yaml"], check=True)

    time.sleep(4)
    webhooks = [
        wh
        for wh in requests.get(
            "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
        ).json()
        if wh["config"]["url"] == "https://example.com"
    ]
    assert len(webhooks) == 0
