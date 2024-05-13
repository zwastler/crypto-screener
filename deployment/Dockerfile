FROM python:3.12-slim as base

ARG ENVIRONMENT

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

FROM base AS builder

RUN pip install -U pip

COPY requirements.txt requirements.txt
RUN pip install --require-hashes --prefix=/install -r requirements.txt

FROM base

RUN groupadd --gid=800 -r unprivileged \
    && useradd --uid=800 --gid=800 --no-log-init -r unprivileged

COPY --from=builder /install /usr/local
COPY src /app
WORKDIR /app

CMD ["python", "main.py"]