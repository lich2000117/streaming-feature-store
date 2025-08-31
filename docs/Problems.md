# Technical Problems & Solutions

## 1. Avro Deserialization Issue
**Problem:** Stream processor crashed with UTF-8 decode error: `'utf-8' codec can't decode byte 0x8f`
- **Root Cause:** Data generators produce binary Avro data, but stream processor expected UTF-8 JSON
- **Solution:** Added Avro deserialization support with schema loading from `schemas/` directory
- **Key Learning:** Serialization format mismatch between producer/consumer is a common streaming issue

## 2. Redis Type Compatibility
**Problem:** Redis failed to store boolean and None values: `Invalid input of type: 'bool'`
- **Root Cause:** Redis only accepts strings, bytes, numbers - not Python booleans/None
- **Solution:** Added `_serialize_for_redis()` method to convert booleans to "true"/"false" strings and None to "null"
- **Key Learning:** Always consider data type compatibility when integrating with external systems

## 3. Schema Evolution Strategy
**Problem:** Need backward compatibility when updating Avro schemas
- **Solution:** Used versioned schema files (transactions.v1.avsc, v2.avsc) with proper field defaults
- **Key Learning:** Plan schema evolution from day one to avoid breaking downstream consumers

## 4. PyFlink vs Simplified Processing
**Problem:** Complex PyFlink setup vs development speed
- **Context:** Two implementations - `feature_job.py` (PyFlink) vs `stream_processor.py` (direct Kafka)
- **PyFlink Benefits:** Exactly-once semantics, advanced windowing, checkpointing, watermarks
- **Simplified Benefits:** Faster development, easier debugging, fewer dependencies  
- **Solution:** Used simplified version for development/testing, PyFlink for production
- **Key Learning:** Start simple for prototyping, then scale to production-grade frameworks

## 5. Code Modularity & Reusability
**Problem:** Duplicate code between PyFlink and simplified processors
- **Root Cause:** Event models, feature computation logic, and utilities were embedded in main files
- **Solution:** Extracted reusable components into modular structure:
  - `models/` - Event/feature models and configuration
  - `processors/` - Feature computation business logic  
  - `sinks/` - Redis output handling
  - `utils/` - Avro deserialization, windowing utilities
- **Key Learning:** Design for reusability from the start - shared logic should be modular
