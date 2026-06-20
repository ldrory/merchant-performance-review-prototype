# Riskified Merchant Performance Review — convenience targets.
#
# First time:   make setup        (creates .venv, installs deps)
# Then:         make ingest       (build the DuckDB facts — no API key needed)
#               make decks        (generate the presentation decks — needs ANTHROPIC_API_KEY)
#               make app          (launch the conversational agent UI — needs ANTHROPIC_API_KEY)
#
# Phases 2/3 need an LLM key: copy .env.example -> .env and set ANTHROPIC_API_KEY
# (or `export ANTHROPIC_API_KEY=sk-...`).

PY := .venv/bin/python
PIP := .venv/bin/pip
m ?= acme   # default merchant for `make chat` / `make decks-one`

.PHONY: setup ingest decks decks-one deliverables chat app test submit-check all clean help

help:
	@echo "Targets: setup | ingest | decks | decks-one m=<id> | deliverables | chat m=<id> | app | test | submit-check | all | clean"

setup:                ## create venv + install dependencies
	python3 -m venv .venv
	$(PIP) install -r requirements.txt

ingest:               ## load + validate + compute facts -> data/processed/riskified.duckdb (ARGS="--input-merchant-profiles=... ")
	$(PY) scripts/ingest.py $(ARGS)

decks:                ## generate a deck for every merchant -> data/output/decks/
	$(PY) scripts/generate_decks.py

decks-one:            ## generate a deck for one merchant: make decks-one m=acme
	$(PY) scripts/generate_decks.py --merchant $(m)

deliverables:         ## copy each merchant's latest deck into deliverables/ (committed samples)
	$(PY) scripts/export_deliverables.py

chat:                 ## CLI agent for one merchant: make chat m=acme
	$(PY) scripts/chat.py --merchant $(m)

app:                  ## launch the Streamlit agent UI (merchant picker = simulated login)
	$(PY) scripts/run_app.py

test:                 ## run the test suite (no network; LLM is stubbed)
	$(PY) -m pytest -q

submit-check:         ## run tests and confirm the sample decks exist
	$(PY) -m pytest -q
	@test -f deliverables/acme_performance_review.pptx \
	  && test -f deliverables/cyberdyne_systems_performance_review.pptx \
	  && test -f deliverables/vandelay_industries_performance_review.pptx \
	  && echo "submit-check OK: tests pass and deliverables present" \
	  || (echo "submit-check FAILED: run 'make decks && make deliverables'"; exit 1)

all: ingest decks     ## ingest then generate all decks

clean:                ## remove the DuckDB and generated outputs (keeps deliverables/)
	rm -f data/processed/*.duckdb
	rm -rf data/output/decks/* data/output/charts/* data/output/quality/*
