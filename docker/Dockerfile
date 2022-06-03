# Base of all section, install the apt packages
FROM ubuntu:22.04 as base-all
LABEL maintainer "info@camptocamp.org"

RUN --mount=type=cache,target=/var/lib/apt/lists \
    --mount=type=cache,target=/var/cache,sharing=locked \
    apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --assume-yes --no-install-recommends \
        python3-pip python3-wheel

# Used to convert the locked packages by poetry to pip requirements format
FROM base-all as poetry

# Install poetry
WORKDIR /tmp
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache \
    python3 -m pip install --disable-pip-version-check --requirement=requirements.txt \
    && rm requirements.txt

# Do the conversion
COPY poetry.lock pyproject.toml ./
RUN poetry export --output=requirements.txt \
    && poetry export --dev --output=requirements-dev.txt

# Do the lint, used by the tests
FROM base-all as test

RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,from=poetry,source=/tmp,target=/poetry \
    python3 -m pip install --disable-pip-version-check --requirement=/poetry/requirements-dev.txt

WORKDIR /app
COPY * ./

# The image used to run the application
FROM base-all as runtime

RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,from=poetry,source=/tmp,target=/poetry \
    python3 -m pip install --disable-pip-version-check --requirement=/poetry/requirements.txt

WORKDIR /app
COPY operator_.py ./
CMD ["kopf", "run", "operator_.py"]
