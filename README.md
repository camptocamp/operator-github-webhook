# GitHub webhook operator

This operator can be used to create webhook on GitHub from a kubernetes object.

## Install

```
helm repo add operator-github-webhook https://camptocamp.github.io/operator-github-webhook/
helm install my-release operator-github-webhook
```

## Example

With the following [k8s object](./tests/webhook.yaml) to create a webhook on this repository.

## Configuration

The operator is configured with environment variables:

- `GITHUB_TOKEN` (required): GitHub token used to manage the webhooks,
  it needs the `admin:repo_hook` scope (or the `Webhooks: Read and write` permission).
- `GITHUB_API_URL` (optional): base URL of the GitHub API, defaults to `https://api.github.com`.
- `GITHUB_WEBHOOK_SECRET` (optional): default webhook secret, can be overridden in the k8s object.
- `LOG_LEVEL` (optional): defaults to `INFO`.
- `REQUESTS_TIMEOUT` (optional): timeout in seconds of the GitHub API requests, defaults to `10`.

## Contributing

Install the pre-commit hooks:

```bash
pip install pre-commit
pre-commit install --allow-missing-config
```
