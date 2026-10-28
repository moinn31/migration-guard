install:
	pip install -r backend/requirements.txt
up:
	docker compose up -d
api:
	uvicorn backend.main:app --reload
openapi:
	python -m backend.export_openapi
test:
	PYTHONPATH=. pytest -q
eval:
	PYTHONPATH=. python -m evaluation.run --config evaluation/config.yaml --max_workers 2
