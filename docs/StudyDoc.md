# Streaming Schemas & Real-Time Fraud — Mini README

A short, straight-to-the-point guide to what changed, why it broke, and how it now works.

---

## TL;DR

Real-time scoring underperformed while training/offline looked great. Fixed three issues:

1. **Feature mismatch** — model expected **16** features; Feast exposed **4** → **updated FeatureViews to 16**.
2. **Race condition** — API read from Feast **before** processor wrote → **write→ack→then score** (or pass features inline).
3. **Model inputs** — feature engineering & generator erased fraud signals → **tuned generator + added robust features + relaxed cleaning**.

Result: Real-time performance ≈ offline.

---

## Mental Model: Batch vs Streaming

**Batch (schema-on-read)**
Files → Process → *discover* schema → transform. Flexible; late validation.

**Streaming (schema-on-write)**
Define schema → validate → stream. Contracts are rigid; validate early.

---

## Avro + Schema Registry (Why it matters)

* **Contract** between producers/consumers.
* **Compatibility** across versions (add optional fields with defaults).
* **Wire format**: `[0x00][schema_id (4 bytes)][avro_binary...]` — tiny and fast.

**Producer flow:** register schema → get id → publish messages with id.
**Consumer flow:** read id → fetch schema → deserialize safely.

---

## Partitioning (Keep related events together)

| Stream          | Key         | Why it matters                 |
| --------------- | ----------- | ------------------------------ |
| `txn.events`    | `card_id`   | Detect per-card fraud patterns |
| `click.events`  | `user_id`   | User-level personalization     |
| `device.events` | `device_id` | Device fingerprinting          |

---

## Schema Evolution — Do / Don’t

**Do (backward-compatible):**

* Add **optional** fields with sensible defaults.
* Extend enums with new symbols.

**Don’t (breaking):**

* Rename fields, change types, or remove required fields.

**Rollout:** deploy new schema → update consumers → update producers → deprecate old.

---

## Producer / Consumer (minimal)

**Producer (pseudo-Python):**

```python
producer.produce(
  topic="txn.events",
  key=event["card_id"],
  value=event,
  value_schema=transactions_v2_schema
)
```

**Consumer (Flink idea):**

```python
kafka_source = AvroKafkaSource("txn.events", schema_registry_url)
stream.key_by(card_id).process(TransactionFeatureProcessor())
```

---

## Postmortem & Fixes (the short version)

1. **Feature mismatch (16 vs 4)**

* Updated Feast `FeatureView` to expose **all 16** model inputs.
* Ran `feast apply` + materialization/backfill where needed.
* Added **CI schema-drift test** (fail build on contract change).

2. **Race (read-before-write)**

* Reordered: **write to Feast → confirm → call scoring API**.
* Added retry/backoff.
* Optional: **inline features** in the scoring request to bypass store latency.

3. **Model inputs (feature engineering & generator)**

* Fraud generator: realistic small test txns (\$1–5), moderate high-amount multipliers (2–3.5×), sane round-amounts, geo/IP signals.
* New features: `small_amount_ratio`, `round_amount_ratio`, `amount_zscore`, `device_reuse_ratio`, `is_high_risk_country`, etc.
* Cleaning: relaxed to **3× IQR** so we **don’t delete the signal**.
* Added unit tests on **feature distributions** + **canary A/B**.

---

## Quick Checks (copy/paste)

```bash
# Feast exposes 16 features
feast registry-dump | jq '.feature_views[] | select(.name=="transaction_stats_5m") | .features | length'

# E2E scoring test
curl -s -X POST http://inference-api:8080/score/fraud \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"test-123","account_id":"acc-1","amount":37.5,"ts":"2025-09-03T02:45:00Z"}'

# No-missing-features metric
curl -s http://inference-api:8080/metrics | grep fraud_features_present_total
```

**Expected:** 16 features present, stable scores, no missing-feature warnings.

---

## Guardrails (keep it fixed)

* **Contract tests**: model schema ↔ processor ↔ Feast.
* **Inline-features path**: prefer request-time join for fresh reads.
* **Monitoring**: PSI/KS weekly; alert on feature nulls & schema drift.
* **CI**: fail on schema incompatibility or missing features.

---

## Real-Time Debugging (September 2025)

After initial fixes, real-time still underperformed. **Root cause**: Feature type conversion issues.

### **Debugging Process**
1. **Added comprehensive logging** to trace feature pipeline: Redis → parsing → model input
2. **Found boolean conversion bug**: Redis strings `'true'/'false'` → kept as strings → model got wrong inputs
3. **Fixed parsing order**: Parse booleans **before** numeric conversion
4. **Verified with debug output**: Feature vectors now properly differentiated

### **Key Findings**
- Boolean features: `is_suspicious_ip: True (type: <class 'bool'>)` ✅
- Model scores: Range 0.009 → 0.999 (working properly) ✅
- High fraud detection: `actual_fraud: True` → `prediction_score: 0.999` ✅

### **Final State**
- Feature parsing: **Fixed** boolean/string conversion 
- Model input: **Verified** correct feature vectors
- Real-time accuracy: **Matches** offline performance
- Threshold: **Lowered** to 0.3 for better sensitivity

---

## Interview Soundbite

> "I treated the model input schema as an API contract. We fixed real-time gaps by aligning Feast to 16 features, removing a read-before-write race, and restoring fraud signal via generator + features. When real-time still underperformed, I added comprehensive debugging to trace the feature pipeline and found boolean conversion bugs in Redis parsing. Request-time features and schema-drift CI keep it reliable."
