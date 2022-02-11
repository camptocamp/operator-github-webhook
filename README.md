# GitHub webhook operator

This operator can be used to create webhook on GitHub from a kubernetes object.

## Install

```
helm repo add operator-github-webhook https://camptocamp.github.io/operator-github-webhook/
helm install my-release operator-github-webhook
```

## Example

With the following [k8s object](./tests/webhook.yaml) to create a webhook on this repository.
