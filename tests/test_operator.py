import json
import os.path
import subprocess
import time

import pytest
import requests
import yaml


@pytest.fixture
def install_operator(scope="session"):
    with open("operator.yaml", "w") as operator_file:
        subprocess.run(["helm", "template", "test", "."], stdout=operator_file, check=True)
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
    subprocess.run(["kubectl", "delete", "-f", "tests/webhook.yaml"], check=True)

    webhooks = [
        wh
        for wh in requests.get(
            "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
        ).json()
        if wh["config"]["url"] == "https://example.com"
    ]
    assert len(webhooks) == 0

    subprocess.run(["kubectl", "apply", "-f", "tests/webhook.yaml"], check=True)

    webhooks = [
        wh
        for wh in requests.get(
            "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
        ).json()
        if wh["config"]["url"] == "https://example.com"
    ]
    assert len(webhooks) == 1

    subprocess.run(["kubectl", "delete", "-f", "tests/webhook.yaml"], check=True)

    webhooks = [
        wh
        for wh in requests.get(
            "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
        ).json()
        if wh["config"]["url"] == "https://example.com"
    ]
    assert len(webhooks) == 0
