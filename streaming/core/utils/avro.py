"""
Avro serialization/deserialization utilities.

Handles Avro schema loading and message deserialization for Kafka consumers.
"""

import os
import io
from typing import Dict, Any
import structlog
import avro.schema
import avro.io

from streaming.core.models.config import ProcessorConfig

logger = structlog.get_logger(__name__)


class AvroDeserializer:
    """Deserializer for Avro-encoded Kafka messages."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.schemas = {}
        self._load_schemas()
        
    def _load_schemas(self):
        """Load Avro schemas from schema directory."""
        schema_dir = self.config.schema_dir
        
        # Load transaction schema
        tx_schema_path = os.path.join(schema_dir, "transactions.v1.avsc")
        try:
            with open(tx_schema_path, 'r') as f:
                tx_schema = avro.schema.parse(f.read())
                self.schemas['txn.events'] = tx_schema
                logger.info(f"Loaded transaction schema from {tx_schema_path}")
        except Exception as e:
            logger.error(f"Failed to load transaction schema: {e}")
            raise
            
        # Load clickstream schema  
        click_schema_path = os.path.join(schema_dir, "clicks.v1.avsc")
        try:
            with open(click_schema_path, 'r') as f:
                click_schema = avro.schema.parse(f.read())
                self.schemas['click.events'] = click_schema
                logger.info(f"Loaded clickstream schema from {click_schema_path}")
        except Exception as e:
            logger.error(f"Failed to load clickstream schema: {e}")
            raise
            
    def deserialize_message(self, topic: str, message_bytes: bytes) -> Dict[str, Any]:
        """Deserialize Avro message for the given topic."""
        try:
            if topic not in self.schemas:
                raise ValueError(f"No schema found for topic: {topic}")
                
            schema = self.schemas[topic]
            bytes_reader = io.BytesIO(message_bytes)
            decoder = avro.io.BinaryDecoder(bytes_reader)
            reader = avro.io.DatumReader(schema)
            
            return reader.read(decoder)
            
        except Exception as e:
            logger.error(f"Failed to deserialize Avro message for topic {topic}: {e}")
            raise
            
    def get_schema(self, topic: str) -> avro.schema.Schema:
        """Get schema for a specific topic."""
        if topic not in self.schemas:
            raise ValueError(f"No schema found for topic: {topic}")
        return self.schemas[topic]
        
    def list_topics(self) -> list:
        """List all available topics with schemas."""
        return list(self.schemas.keys())


class AvroSerializer:
    """Serializer for Avro-encoded Kafka messages."""
    
    def __init__(self, schema: avro.schema.Schema):
        self.schema = schema
        
    def serialize_message(self, event: Dict[str, Any]) -> bytes:
        """Serialize event to Avro binary format."""
        try:
            writer = avro.io.DatumWriter(self.schema)
            bytes_writer = io.BytesIO()
            encoder = avro.io.BinaryEncoder(bytes_writer)
            writer.write(event, encoder)
            return bytes_writer.getvalue()
        except Exception as e:
            logger.error(f"Failed to serialize event: {e}")
            logger.error(f"Event data: {event}")
            raise
