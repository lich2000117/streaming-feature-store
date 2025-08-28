up:        ## start infra
\tdocker compose -f infra/docker-compose.yml up -d

down:      ## stop infra
\tdocker compose -f infra/docker-compose.yml down -v

seed:      ## start event generators
\tpython generators/txgen.py & python generators/clickgen.py &

run-features: ## submit flink job
\t./infra/bin/flink run -c jobs.FeatureJob flink/jobs/feature_job.py

serve:     ## run inference service
\tuvicorn services.inference.app:app --host 0.0.0.0 --port 8080 --reload

train:     ## train & register model
\tpython ml/train.py

test-latency:
\tk6 run loadtest/k6_inference_test.js

drift-check:
\tpython ml/drift_check.py

replay:
\tpython flink/tools/replay_dlq.py --file $(file)
