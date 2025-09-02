## 🚀 **Quick Test Examples**

### **1. Basic Fraud Scoring**
```bash
curl -X POST http://localhost:8080/score/fraud \
  -H "Content-Type: application/json" \
  -d '{"card_id": "card_00001234", "transaction_amount": 150.0}'
```

### **2. High-Risk Transaction**
```bash
curl -X POST http://localhost:8080/score/fraud \
  -H "Content-Type: application/json" \
  -d '{"card_id": "card_00030479", "transaction_amount": 5000.0, "mcc_code": "6011"}' | grep "score"
```

### **3. Personalization**
```bash
curl -X POST http://localhost:8080/score/personalization \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_00005678", "item_category": "electronics"}'
```

### **4. Batch Scoring**
```bash
curl -X POST http://localhost:8080/score/batch \
  -H "Content-Type: application/json" \
  -d '{
    "model_type": "fraud_detection",
    "batch_id": "test_batch_001",
    "requests": [
      {"card_id": "card_00001234", "transaction_amount": 100.0},
      {"card_id": "card_00030479", "transaction_amount": 2000.0}
    ]
  }'
```

### **5. Health Check**
```bash
curl http://localhost:8080/health
```

### **6. Python Example**
```python
import requests

response = requests.post(
    "http://localhost:8080/score/fraud",
    json={"card_id": "card_00001234", "transaction_amount": 150.0}
)
print(response.json()["fraud_score"])
```

### **7. Use Makefile**
```bash
make test-api
```