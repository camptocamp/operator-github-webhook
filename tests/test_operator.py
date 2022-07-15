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
    """Install the operator"""
    del scope

    # Create the operator
    LOG.warning("Create operator: %s", datetime.datetime.now())
    with open("operator.yaml", "w", encoding="utf-8") as operator_file:
        subprocess.run(
            [
                "helm",
                "template",
                "test",
                ".",
                "--namespace=default",
                f"--set=image.tag=latest,env.GITHUB_TOKEN={os.environ['GITHUB_TOKEN']},"
                "env.LOG_LEVEL=DEBUG,env.ENVIRONMENT=test",
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


def _assert_webhooks(nb: int, hook_type: str = None, url: str = None, secret: str = None):
    for _ in range(10):
        webhooks = [
            webhook
            for webhook in requests.get(
                "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
                headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
            ).json()
            if webhook["config"]["url"].startswith("https://example.com")
        ]
        if (
            len(webhooks) == nb
            and all(wh["config"]["content_type"] == hook_type for wh in webhooks)
            and all(wh["config"]["url"] == url for wh in webhooks)
            and all(wh["config"]["secret"] == secret for wh in webhooks)
        ):
            return
        time.sleep(1)
    assert len(webhooks) == nb, "The webhooks didn't match: \n" + yaml.dump(webhooks)
    assert all(wh["config"]["content_type"] == hook_type for wh in webhooks), [
        wh["config"]["content_type"] for wh in webhooks
    ]
    assert all(wh["config"]["url"] == url for wh in webhooks), [wh["config"]["url"] for wh in webhooks]


def test_operator(install_operator):
    del install_operator

    # Initialize the source and the config
    subprocess.run(["kubectl", "delete", "-f", "tests/webhook.yaml"])

    # Clean the old webhook
    webhooks = requests.get(
        "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
        headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
    )
    webhooks.raise_for_status()
    for webhook in webhooks.json():
        if webhook["config"]["url"].startswith("https://example.com"):
            requests.delete(
                f"https://api.github.com/repos/camptocamp/operator-github-webhook/hooks/{webhook['id']}",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": AUTH_HEADER,
                },
            )
    _assert_webhooks(0)

    # Test creation
    LOG.warning("Test creation: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "apply", "-f", "tests/webhook.yaml"], check=True)
    _assert_webhooks(1, "json", "https://example.com", "my-secret")

    # Test modification
    LOG.warning("Test modification: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "apply", "-f", "tests/webhook-form.yaml"], check=True)
    _assert_webhooks(1, "form", "https://example.com", "my-secret")

    # Test remove
    LOG.warning("Test remove: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "delete", "-f", "tests/webhook-form.yaml"], check=True)
    _assert_webhooks(0)
