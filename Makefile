export DOCKER_BUILDKIT=1

.PHONY: build
build:
	docker build --tag=camptocamp/github-webhook-operator docker
	docker tag camptocamp/github-webhook-operator ghcr.io/camptocamp/github-webhook-operator

.PHONY: build-test
build-test:
	docker build --target=test --tag=camptocamp/github-webhook-operator-test docker

.PHONY: prospector
prospector: build-test
	docker run --rm camptocamp/github-webhook-operator-test prospector --die-on-tool-error --output=pylint operator_.py

.PHONY: tests
tests:
	pytest --verbose
