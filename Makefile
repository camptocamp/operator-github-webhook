
.PHONY: build
build:
	docker build --tag=camptocamp/github-webhook-operator docker

.PHONY: build-test
build-test:
	docker build --target=test --tag=camptocamp/github-webhook-operator-test docker

.PHONY: prospector
prospector: build-test
	docker run camptocamp/github-webhook-operator-test prospector --output=pylint operator

.PHONY: tests
tests:
	pytest --verbose
