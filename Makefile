# Midwest HSR pipeline. `make all` reproduces every output from the internet.
# `make mirror` uses GitHub-hosted fallbacks only (Census 2023 boundaries, Natural Earth rail).
PY ?= python3

.PHONY: install fetch mirror build analyze export report qa test all clean

install:
	$(PY) -m pip install -e ".[dev]"
	npm install -g mapshaper@0.6

fetch:
	hsr fetch

mirror:
	hsr fetch --mirror

build:
	hsr build

analyze:
	hsr analyze

export:
	hsr export

report:
	hsr report

qa:
	hsr qa

test:
	$(PY) -m pytest -q

all: fetch build analyze export report qa

clean:
	rm -rf data/interim data/processed web/data docs/generated
