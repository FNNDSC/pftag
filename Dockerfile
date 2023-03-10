# Python version can be changed, e.g.
# FROM python:3.8
# FROM docker.io/fnndsc/conda:python3.10.2-cuda11.6.0
FROM docker.io/python:3.11.0-slim-bullseye

LABEL org.opencontainers.image.authors="FNNDSC <rudolph.pienaar@childrens.harvard.edu>" \
      org.opencontainers.image.title="Leg-Length Discrepency - Dynamic Compute Flow" \
      org.opencontainers.image.description="A ChRIS plugin that dynamically builds a workflow to compute length discrepencies from extremity X-Rays"

WORKDIR /usr/local/src/pflog

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
ARG extras_require=none
RUN pip install ".[${extras_require}]"

RUN apt update && apt -y install telnet procps curl

CMD ["pftag", "--man"]
