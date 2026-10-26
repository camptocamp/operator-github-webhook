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

MOCK_NAME = "github-mock"
MOCK_NAMESPACE = "github-mock"
MOCK_PORT = 8080
# URL of the mock used by the tests, through kubectl port-forward
LOCAL_MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"
# URL of the mock used by the operator, inside the cluster
IN_CLUSTER_MOCK_URL = f"http://{MOCK_NAME}.{MOCK_NAMESPACE}.svc.cluster.local:{MOCK_PORT}"
HOOKS_URL = f"{LOCAL_MOCK_URL}/repos/camptocamp/operator-github-webhook/hooks"
AUTH_HEADER = "Bearer test-token"


def _kubectl_apply_stdin(manifest: bytes) -> None:
    subprocess.run(["kubectl", "apply", "--filename=-"], input=manifest, check=True)


@pytest.fixture(scope="session")
def mock_github_api():
    """Deploy the GitHub API mock and expose it locally with a port-forward"""
    LOG.warning("Create GitHub API mock: %s", datetime.datetime.now())
    _kubectl_apply_stdin(
        subprocess.run(
            ["kubectl", "create", "namespace", MOCK_NAMESPACE, "--dry-run=client", "--output=yaml"],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
    )
    _kubectl_apply_stdin(
        subprocess.run(
            [
                "kubectl",
                "create",
                "configmap",
                MOCK_NAME,
                f"--namespace={MOCK_NAMESPACE}",
                "--from-file=mock_github_api.py=tests/mock_github_api.py",
                "--dry-run=client",
                "--output=yaml",
            ],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
    )
    subprocess.run(["kubectl", "apply", "--filename=tests/mock.yaml"], check=True)
    subprocess.run(
        [
            "kubectl",
            "rollout",
            "status",
            f"--namespace={MOCK_NAMESPACE}",
            f"deployment/{MOCK_NAME}",
            "--timeout=180s",
        ],
        check=True,
    )

    port_forward = subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            f"--namespace={MOCK_NAMESPACE}",
            f"service/{MOCK_NAME}",
            f"{MOCK_PORT}:{MOCK_PORT}",
        ]
    )
    try:
        for _ in range(60):
            try:
                requests.get(f"{LOCAL_MOCK_URL}/healthz", timeout=1).raise_for_status()
                break
            except requests.RequestException:
                time.sleep(1)
        else:
            pytest.fail("The GitHub API mock didn't start")
        LOG.warning("GitHub API mock created: %s", datetime.datetime.now())

        yield LOCAL_MOCK_URL
    finally:
        port_forward.terminate()
        port_forward.wait(timeout=10)
        subprocess.run(["kubectl", "delete", "--filename=tests/mock.yaml"], check=False)


@pytest.fixture
def install_operator(mock_github_api):
    """Install the operator"""
    del mock_github_api

    # Create the operator
    LOG.warning("Create operator: %s", datetime.datetime.now())
    try:
        with open("operator.yaml", "w", encoding="utf-8") as operator_file:
            subprocess.run(
                [
                    "helm",
                    "template",
                    "test",
                    ".",
                    "--namespace=default",
                    "--set-json=args=" + json.dumps(["--debug"]),
                    "--set-json=env="
                    + json.dumps(
                        [
                            {"name": "GITHUB_TOKEN", "value": os.environ.get("GITHUB_TOKEN", "test-token")},
                            {"name": "GITHUB_API_URL", "value": IN_CLUSTER_MOCK_URL},
                            {"name": "LOG_LEVEL", "value": "DEBUG"},
                            {"name": "ENVIRONMENT", "value": "test"},
                        ]
                    ),
                    "--set=image.tag=latest,crd.suffix=test,crd.shortSuffix=t",
                ],
                stdout=operator_file,
                check=True,
            )
        subprocess.run(["kubectl", "apply", "--filename=operator.yaml"], check=True)

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
                and len(
                    [
                        c
                        for c in pods["items"][0].get("status", {}).get("conditions", {})
                        if c["status"] != "True"
                    ]
                )
                == 0
            ):
                success = True
                break
            time.sleep(1)
        assert success, "The operator didn't run correctly: \n" + yaml.dump(pods)
        LOG.warning("Operator created: %s", datetime.datetime.now())

        yield
    finally:
        # We should have the pod to be able to extract the logs
        # subprocess.run(["kubectl", "delete", "--filename=operator.yaml"], check=True)
        os.remove("operator.yaml")


def _assert_webhooks(
    nb: int, hook_type: str | None = None, url: str | None = None, secret: str | None = None
):
    webhooks: list = []
    for _ in range(10):
        webhooks = [
            webhook
            for webhook in requests.get(
                HOOKS_URL,
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
    subprocess.run(["kubectl", "delete", "--filename=tests/webhook.yaml"], check=False)

    # Clean the old webhook
    webhooks = requests.get(
        HOOKS_URL,
        headers={"Accept": "application/vnd.github.v3+json", "Authorization": AUTH_HEADER},
    )
    webhooks.raise_for_status()
    for webhook in webhooks.json():
        if webhook["config"]["url"].startswith("https://example.com"):
            requests.delete(
                f"{HOOKS_URL}/{webhook['id']}",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": AUTH_HEADER,
                },
            )
    _assert_webhooks(0)

    # Test creation
    LOG.warning("Test creation: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "apply", "--filename=tests/webhook.yaml"], check=True)
    _assert_webhooks(1, "json", "https://example.com", "my-secret")

    # Test modification
    LOG.warning("Test modification: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "apply", "--filename=tests/webhook-form.yaml"], check=True)
    _assert_webhooks(1, "form", "https://example.com", "my-secret")

    # Test remove
    LOG.warning("Test remove: %s", datetime.datetime.now())
    subprocess.run(["kubectl", "delete", "--filename=tests/webhook-form.yaml"], check=True)
    _assert_webhooks(0)
