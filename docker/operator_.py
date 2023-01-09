#!/usr/bin/env python3

import datetime
import logging
import os
from typing import Any, Dict

import kopf
import requests

AUTH_HEADER = f"Bearer {os.environ['GITHUB_TOKEN']}"
ENVIRONMENT: str = os.environ["ENVIRONMENT"]
TIMEOUT = int(os.environ.get("REQUESTS_TIMEOUT", "10"))


@kopf.on.startup()
def startup(settings: kopf.OperatorSettings, logger: kopf.Logger, **_) -> None:
    settings.posting.level = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO"))
    if "KOPF_SERVER_TIMEOUT" in os.environ:
        settings.watching.server_timeout = int(os.environ["KOPF_SERVER_TIMEOUT"])
    if "KOPF_CLIENT_TIMEOUT" in os.environ:
        settings.watching.client_timeout = int(os.environ["KOPF_CLIENT_TIMEOUT"])
    logger.info("GitHub WebHook creator started")
    logger.debug("Start date: %s", datetime.datetime.now())


def create_webhook(spec: kopf.Spec, logger: kopf.Logger) -> Dict[str, Any]:
    webhooks_response = requests.get(
        f"https://api.github.com/repos/{spec['repository']}/hooks",
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": AUTH_HEADER,
        },
        timeout=TIMEOUT,
    )
    logger.debug("Get WebHooks:\n%s", webhooks_response.text)
    if not webhooks_response.ok:
        raise kopf.TemporaryError(
            f"Unable to get webhooks for repository {spec['repository']}:\n{webhooks_response.text}",
            delay=60,
        )
    webhooks = webhooks_response.json()

    for webhook in webhooks:
        if (
            webhook["config"]["url"] == spec["url"]
            and webhook["config"]["content_type"] == spec.get("contentType", "json")
            and webhook["config"]["secret"] == spec["secret"]
        ):
            return {"ghId": webhook["id"]}

    result = requests.post(
        f"https://api.github.com/repos/{spec['repository']}/hooks",
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": AUTH_HEADER,
        },
        json={
            "config": {
                "content_type": spec.get("contentType", "json"),
                "url": spec["url"],
                "secret": spec["secret"],
            }
        },
        timeout=TIMEOUT,
    )
    logger.debug("Create WebHook:\n%s", result.text)
    if not result.ok:
        raise kopf.TemporaryError(
            f"Unable to create webhook {spec['url']} on repository {spec['repository']}:\n%{result.text}",
        )
    logger.info(
        "Webhook %s on repository %s created",
        spec["url"],
        spec["repository"],
    )
    return {"ghId": result.json()["id"]}


def delete_webhook(url: str, repository: str, id_: int, logger: kopf.Logger) -> None:
    result = requests.delete(
        f"https://api.github.com/repos/{repository}/hooks/{id_}",
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": AUTH_HEADER,
        },
        timeout=TIMEOUT,
    )
    if not result.ok:
        logger.warning("Unable to delete webhook %s on repository %s: %s", url, repository, result.text)
    else:
        logger.info("Webhook %s on repository %s deleted", url, repository)
        logger.debug(result.text)


@kopf.on.resume("camptocamp.com", "v3", "githubwebhooks", field="spec.environment", value=ENVIRONMENT)
@kopf.on.create("camptocamp.com", "v3", "githubwebhooks", field="spec.environment", value=ENVIRONMENT)
async def create(meta: kopf.Meta, spec: kopf.Spec, logger: kopf.Logger, **_) -> Dict[str, Any]:
    logger.info("Create, Name: %s, Namespace: %s", meta.get("name"), meta.get("namespace"))

    return create_webhook(spec, logger)


@kopf.on.delete("camptocamp.com", "v3", "githubwebhooks", field="spec.environment", value=ENVIRONMENT)
async def delete(meta: kopf.Meta, spec: kopf.Spec, status: kopf.Status, logger: kopf.Logger, **_) -> None:
    logger.info(
        "Delete, Name: %s, Namespace: %s, Status: %s", meta.get("name"), meta.get("namespace"), status
    )
    create_status = status.get("create/spec.environment", {})
    if "ghId" in create_status:
        delete_webhook(spec["url"], spec["repository"], create_status["ghId"], logger)


@kopf.on.update("camptocamp.com", "v3", "githubwebhooks")
async def update(**_) -> Dict[str, Any]:
    raise kopf.PermanentError("The object cannot be changed.")
