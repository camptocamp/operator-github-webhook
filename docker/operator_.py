#!/usr/bin/env python3

import datetime
import hashlib
import logging
import os
from typing import Any, Optional, cast

import kopf
import requests

AUTH_HEADER = f"Bearer {os.environ['GITHUB_TOKEN']}"
ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "")
TIMEOUT = int(os.environ.get("REQUESTS_TIMEOUT", "10"))


def _hash(spec: kopf.Spec) -> str:
    secret = spec.get("secret", os.environ.get("GITHUB_WEBHOOK_SECRET"))
    return hashlib.sha256(
        f"{spec['repository']}:{spec['url']}:{spec['contentType']}:{secret}".encode(),
    ).hexdigest()


@kopf.on.startup()
def startup(settings: kopf.OperatorSettings, logger: kopf.Logger, **_: Any) -> None:
    """Startup the operator."""
    settings.posting.level = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO"))
    if "KOPF_SERVER_TIMEOUT" in os.environ:
        settings.watching.server_timeout = int(os.environ["KOPF_SERVER_TIMEOUT"])
    if "KOPF_CLIENT_TIMEOUT" in os.environ:
        settings.watching.client_timeout = int(os.environ["KOPF_CLIENT_TIMEOUT"])
    logger.info("GitHub WebHook creator started")
    logger.debug("Start date: %s", datetime.datetime.now(datetime.timezone.utc))


def create_webhook(spec: kopf.Spec, logger: kopf.Logger) -> dict[str, Any]:
    """Create the webhook."""
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
        message = f"Unable to get webhooks for repository {spec['repository']}:\n{webhooks_response.text}"
        raise kopf.TemporaryError(message, delay=60)
    webhooks = webhooks_response.json()

    for webhook in webhooks:
        if (
            webhook["config"]["url"] == spec["url"]
            and webhook["config"]["content_type"] == spec.get("contentType", "json")
            and webhook["config"]["secret"] == spec.get("secret", os.environ.get("GITHUB_WEBHOOK_SECRET"))
        ):
            return {"ghId": webhook["id"]}

    for webhook in webhooks:
        if webhook["config"]["url"] == spec["url"]:
            delete_webhook(spec["url"], spec["repository"], webhook["id"], logger)

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
                "secret": spec.get("secret", os.environ.get("GITHUB_WEBHOOK_SECRET")),
            },
        },
        timeout=TIMEOUT,
    )
    logger.debug("Create WebHook:\n%s", result.text)
    if not result.ok:
        message = (
            f"Unable to create webhook {spec['url']} on repository {spec['repository']}:\n%{result.text}"
        )
        raise kopf.TemporaryError(message)
    logger.info(
        "Webhook %s on repository %s created",
        spec["url"],
        spec["repository"],
    )
    return {"ghId": result.json()["id"], "hash": _hash(spec)}


def delete_webhook(url: str, repository: str, id_: int, logger: kopf.Logger) -> None:
    """Delete the webhook."""
    result = requests.delete(
        f"https://api.github.com/repos/{repository}/hooks/{id_}",
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": AUTH_HEADER,
        },
        timeout=TIMEOUT,
    )
    if not result.ok:
        logger.warning(
            "Unable to delete webhook %s on repository %s: %s",
            url,
            repository,
            result.text,
        )
    else:
        logger.info("Webhook %s on repository %s deleted", url, repository)
        logger.debug(result.text)


@kopf.on.create("camptocamp.com", "v4", f"githubwebhooks{ENVIRONMENT}")
async def create(meta: kopf.Meta, spec: kopf.Spec, logger: kopf.Logger, **_: Any) -> dict[str, Any]:
    """Manage the creation of the webhook."""
    logger.info("Create, Name: %s, Namespace: %s", meta.get("name"), meta.get("namespace"))

    return create_webhook(spec, logger)


def get_status(status: kopf.Status) -> dict[str, Any]:
    """Get the status of the webhook."""
    for name in ("update", "create"):
        if name in status:
            return cast(dict[str, Any], status[name])
    return {}


@kopf.on.resume("camptocamp.com", "v4", f"githubwebhooks{ENVIRONMENT}")
@kopf.on.update("camptocamp.com", "v4", f"githubwebhooks{ENVIRONMENT}")
async def update(
    meta: kopf.Meta,
    spec: kopf.Spec,
    status: kopf.Status,
    logger: kopf.Logger,
    **_: Any,
) -> Optional[dict[str, Any]]:
    """Manage the update or resume of the webhook."""
    logger.info(
        "Update or resume, Name: %s, Namespace: %s",
        meta.get("name"),
        meta.get("namespace"),
    )
    last_status = get_status(status)
    if "ghId" in last_status:
        if last_status["hash"] == _hash(spec):
            return last_status
        delete_webhook(spec["url"], spec["repository"], last_status["ghId"], logger)

    return create_webhook(spec, logger)


@kopf.on.delete("camptocamp.com", "v4", f"githubwebhooks{ENVIRONMENT}")
async def delete(
    meta: kopf.Meta,
    spec: kopf.Spec,
    status: kopf.Status,
    logger: kopf.Logger,
    **_: Any,
) -> None:
    """Manage the deletion of the webhook."""
    logger.info(
        "Delete, Name: %s, Namespace: %s, Status: %s",
        meta.get("name"),
        meta.get("namespace"),
        status,
    )
    last_status = get_status(status)
    if "ghId" in last_status:
        delete_webhook(spec["url"], spec["repository"], last_status["ghId"], logger)
