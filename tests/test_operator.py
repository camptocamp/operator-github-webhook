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
        subprocess.run(
            [
                "helm",
                "template",
                "test",
                ".",
                f"--set=env.GITHUB_TOKEN={os.environ['GITHUB_TOKEN']},env.LOGLEVEL=DEBUG",
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

    subprocess.run(["kubectl", "apply", "-f", "tests/webhook-form.yaml"], check=True)

    for _ in range(10):
        webhooks = [
            wh
            for wh in requests.get(
                "https://api.github.com/repos/camptocamp/operator-github-webhook/hooks",
                headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
            ).json()
            if wh["config"]["url"] == "https://example.com" and wh["config"]["content_type"] == "form"
        ]
        if len(webhooks) == 1:
            break
        else:
            time.sleep(1)
    assert len(webhooks) == 1
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
