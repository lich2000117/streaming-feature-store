# 🚀 Streaming Feature Store - Production Container Orchestration

# === CORE INFRASTRUCTURE ===
up:         ## Start core infrastructure (kafka, redis, schema-registry)
	docker compose -f infra/docker-compose.yml up -d

up-all:     ## Start complete platform (all services)
	docker compose -f infra/docker-compose.yml --profile all up -d

down:       ## Stop all services and cleanup
	docker compose -f infra/docker-compose.yml --profile all down -v

# === SERVICE MANAGEMENT ===
generate:   ## Start event generators
	docker compose -f infra/docker-compose.yml --profile generators up -d

stream:     ## Start stream processing
	docker compose -f infra/docker-compose.yml --profile streaming up -d

serve:      ## Start inference API
	docker compose -f infra/docker-compose.yml --profile inference up -d

train:      ## Run ML training pipeline
	docker compose -f infra/docker-compose.yml --profile training up training-job

feast:      ## Start feature store server
	docker compose -f infra/docker-compose.yml --profile feast up -d

monitor:    ## Start monitoring stack (prometheus, grafana)
	docker compose -f infra/docker-compose.yml --profile monitoring up -d

# === TESTING & VALIDATION ===
test:       ## Test inference API endpoints
	@echo "🧪 Testing Fraud Detection API..."
	curl -X POST http://localhost:8080/score/fraud \
		-H "Content-Type: application/json" \
		-d '{"card_id": "card_00001234", "transaction_amount": 150.0}' | jq .
	@echo "\n🧪 Testing Personalization API..."
	curl -X POST http://localhost:8080/score/personalization \
		-H "Content-Type: application/json" \
		-d '{"user_id": "user_00005678", "item_id": "item_electronics_001"}' | jq .

health:     ## Check service health status
	@echo "=== 🏥 Health Check ==="
	@echo "📊 Kafka:"
	@docker exec kafka rpk cluster info || echo "❌ Kafka unhealthy"
	@echo "\n💾 Redis:" 
	@docker exec redis redis-cli ping || echo "❌ Redis unhealthy"
	@echo "\n🚀 API:"
	@curl -s http://localhost:8080/health | jq . || echo "❌ API unhealthy"

status:     ## Show service status
	@echo "=== 📋 Service Status ==="
	@docker compose -f infra/docker-compose.yml ps

# === OBSERVABILITY ===
logs:       ## View all service logs
	docker compose -f infra/docker-compose.yml logs -f

logs-api:   ## View inference API logs
	docker compose -f infra/docker-compose.yml logs -f inference-api

logs-stream: ## View stream processor logs
	docker compose -f infra/docker-compose.yml logs -f stream-processor

logs-gen:   ## View generator logs
	docker compose -f infra/docker-compose.yml logs -f txn-generator click-generator

# === DATA INSPECTION ===
inspect:    ## Inspect data flow (kafka + redis)
	@echo "=== 📨 Kafka Topics ==="
	@docker exec kafka rpk topic list
	@echo "\n=== 📦 Sample Events ==="
	@echo "Transactions:"
	@timeout 3 docker exec kafka rpk topic consume txn.events --num 2 2>/dev/null || echo "No messages yet"
	@echo "\nClicks:" 
	@timeout 3 docker exec kafka rpk topic consume click.events --num 2 2>/dev/null || echo "No messages yet"
	@echo "\n=== 🗂️ Feature Store ==="
	@docker exec redis redis-cli --scan --pattern "features:*" | head -5 || echo "No features yet"

# === DEVELOPMENT ===
build:      ## Build all service images
	docker compose -f infra/docker-compose.yml build

rebuild:    ## Rebuild all images from scratch
	docker compose -f infra/docker-compose.yml build --no-cache

clean:      ## Complete cleanup (containers, volumes, images)
	docker compose -f infra/docker-compose.yml --profile all down -v --remove-orphans
	docker system prune -f

# === QUICK WORKFLOWS ===
demo:       ## 🎬 Complete demo setup
	@echo "🚀 Starting Streaming Feature Store Demo..."
	@echo "⚙️  Starting infrastructure..."
	@make up
	@echo "⏳ Waiting for services..."
	@sleep 10
	@echo "🚀 Starting inference API..."
	@make serve
	@sleep 5
	@echo "✅ Demo ready! Try these commands:"
	@echo "  make generate    # Start event generators"
	@echo "  make stream      # Start feature processing"
	@echo "  make test        # Test the API"
	@echo "  make inspect     # View live data"

urls:       ## Show service URLs
	@echo "🌐 Service URLs:"
	@echo "  Inference API:     http://localhost:8080"
	@echo "  API Docs:          http://localhost:8080/docs"
	@echo "  Kafka UI:          http://localhost:9644" 
	@echo "  Schema Registry:   http://localhost:8081"
	@echo "  MLflow:            http://localhost:5000"
	@echo "  Prometheus:        http://localhost:9090"
	@echo "  Grafana:           http://localhost:3000 (admin/admin123)"

help:       ## Show available commands
	@echo ""
	@echo "🚀 Streaming Feature Store - Container Commands"
	@echo ""
	@echo "🎬 Quick Start:"
	@echo "  make demo        Complete demo setup"
	@echo "  make test        Test API endpoints"
	@echo "  make urls        Show service URLs"
	@echo ""
	@echo "📦 Services:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""