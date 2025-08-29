up:        ## start infra
	docker compose -f infra/docker-compose.yml up -d

down:      ## stop infra
	docker compose -f infra/docker-compose.yml down -v

seed:      ## start event generators  
	source .venv/bin/activate && python generators/txgen.py --events-per-second 10 --duration 3600 &
	source .venv/bin/activate && python generators/clickgen.py --events-per-second 15 --duration 3600 &

run-features: ## run stream processor (simplified Flink alternative)
	source .venv/bin/activate && python flink/stream_processor.py --kafka-servers localhost:9092 --redis-host localhost

run-flink: ## submit actual flink job (requires PyFlink setup)
	./infra/bin/flink run -c jobs.FeatureJob flink/jobs/feature_job.py

serve:     ## run inference service
	uvicorn services.inference.app:app --host 0.0.0.0 --port 8080 --reload

train:     ## train & register model
	python ml/train.py

test-generators: ## test data generators
	source .venv/bin/activate && python generators/test_generators.py

test-features: ## test feature engineering pipeline
	source .venv/bin/activate && python flink/test_stream_processor.py

test-schemas: ## validate avro schemas
	source .venv/bin/activate && python schemas/validate_schemas.py

test-latency: ## run load tests
	k6 run loadtest/k6_inference_test.js

drift-check: ## check for feature drift
	python ml/drift_check.py

replay:   ## replay DLQ events
	python flink/tools/replay_dlq.py --file $(file)

venv:     ## create virtual environment
	python3 -m venv .venv
	source .venv/bin/activate && pip install --upgrade pip

install:  ## install dependencies
	source .venv/bin/activate && pip install -r generators/requirements.txt
	source .venv/bin/activate && pip install -r schemas/requirements.txt  
	source .venv/bin/activate && pip install redis prometheus-client structlog

clean:    ## cleanup
	docker compose -f infra/docker-compose.yml down -v
	rm -rf .venv
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete

help:     ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
