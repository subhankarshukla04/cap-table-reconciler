.PHONY: install seed bake demo-day radar-up history test clean

PY := .venv/bin/python
PIP := .venv/bin/pip

install:
	$(PIP) install -e .
	$(PIP) install httpx selectolax feedparser apscheduler rapidfuzz python-dotenv pytest

seed:
	$(PY) scripts/gen_holders.py
	$(PY) scripts/seed.py

bake:
	$(PY) scripts/bake_cache.py

demo-day:
	$(PY) scripts/demo_day.py
	$(PY) scripts/seed_history.py

radar-up:
	FLASK_RUN_PORT=5001 $(PY) -m radar.app

history:
	@ls -la data/digests/

test:
	$(PY) -m pytest tests/radar/ -v

clean:
	rm -f data/radar.db
	rm -rf data/digests/*.html

help:
	@echo "make install     install deps into .venv"
	@echo "make seed        generate holder fixtures + seed DB"
	@echo "make bake        bake offline scraper cache for 2026-05-11"
	@echo "make demo-day    end-to-end: scrape (cached) -> score -> digest -> bark"
	@echo "make radar-up    start the Flask app on :5001"
	@echo "make history     list archived digest snapshots"
	@echo "make test        run radar/ unit tests"
