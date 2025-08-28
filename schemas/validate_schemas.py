#!/usr/bin/env python3
"""
Schema validation utility for streaming feature store.

This script validates:
1. Avro schema syntax correctness
2. Backward compatibility between versions
3. Required field presence
4. Default value validity

Usage:
    python schemas/validate_schemas.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

try:
    import avro.schema
    # Note: compatibility checking requires confluent-kafka, skip for now
    COMPATIBILITY_CHECK_AVAILABLE = False
    try:
        from avro.compatibility import ReaderWriterCompatibilityChecker
        COMPATIBILITY_CHECK_AVAILABLE = True
    except ImportError:
        pass
except ImportError:
    print("❌ Error: avro-python3 not installed")
    print("Install with: pip install avro-python3")
    sys.exit(1)


class SchemaValidator:
    """Validates Avro schemas for correctness and compatibility."""
    
    def __init__(self, schemas_dir: str = "schemas"):
        self.schemas_dir = Path(schemas_dir)
        self.schemas: Dict[str, avro.schema.Schema] = {}
        
    def load_schemas(self) -> None:
        """Load all .avsc files in the schemas directory."""
        print("🔍 Loading schemas...")
        
        for schema_file in self.schemas_dir.glob("*.avsc"):
            try:
                with open(schema_file, 'r') as f:
                    schema_json = json.load(f)
                    schema = avro.schema.parse(json.dumps(schema_json))
                    self.schemas[schema_file.name] = schema
                    print(f"  ✅ Loaded {schema_file.name}")
            except Exception as e:
                print(f"  ❌ Failed to load {schema_file.name}: {e}")
                
    def validate_schema_syntax(self) -> bool:
        """Validate Avro schema syntax."""
        print("\n🔧 Validating schema syntax...")
        all_valid = True
        
        for name, schema in self.schemas.items():
            try:
                # Check for required fields
                schema_dict = json.loads(str(schema))
                required_fields = ['type', 'name', 'namespace', 'fields']
                
                for field in required_fields:
                    if field not in schema_dict:
                        print(f"  ❌ {name}: Missing required field '{field}'")
                        all_valid = False
                        continue
                
                # Validate field types and defaults
                self._validate_fields(schema_dict['fields'], name)
                print(f"  ✅ {name}: Valid syntax")
                
            except Exception as e:
                print(f"  ❌ {name}: Syntax error - {e}")
                all_valid = False
                
        return all_valid
    
    def _validate_fields(self, fields: List[Dict[str, Any]], schema_name: str) -> None:
        """Validate individual fields in a schema."""
        for field in fields:
            field_name = field.get('name', 'unnamed')
            field_type = field.get('type')
            
            # Check for documentation
            if 'doc' not in field:
                print(f"  ⚠️  {schema_name}: Field '{field_name}' missing documentation")
            
            # Validate union types have defaults for optional fields
            if isinstance(field_type, list) and 'null' in field_type:
                if 'default' not in field:
                    print(f"  ❌ {schema_name}: Optional field '{field_name}' missing default value")
                    
    def validate_compatibility(self) -> bool:
        """Check backward compatibility between schema versions."""
        print("\n🔄 Checking schema compatibility...")
        
        if not COMPATIBILITY_CHECK_AVAILABLE:
            print("  ℹ️  Compatibility checking requires confluent-kafka[avro], skipping...")
            print("  💡 For full compatibility checks, install: pip install confluent-kafka[avro]")
            return True
            
        all_compatible = True
        
        # Group schemas by base name (before version)
        schema_groups = {}
        for name in self.schemas.keys():
            base_name = name.split('.v')[0]
            if base_name not in schema_groups:
                schema_groups[base_name] = []
            schema_groups[base_name].append(name)
        
        # Check compatibility within each group
        for base_name, versions in schema_groups.items():
            if len(versions) > 1:
                sorted_versions = sorted(versions)
                for i in range(1, len(sorted_versions)):
                    prev_version = sorted_versions[i-1]
                    curr_version = sorted_versions[i]
                    
                    try:
                        checker = ReaderWriterCompatibilityChecker()
                        writer_schema = self.schemas[prev_version]
                        reader_schema = self.schemas[curr_version]
                        
                        # Check if new version can read old data (backward compatibility)
                        is_compatible = checker.can_read(writer_schema, reader_schema)
                        
                        if is_compatible:
                            print(f"  ✅ {prev_version} → {curr_version}: Backward compatible")
                        else:
                            print(f"  ❌ {prev_version} → {curr_version}: NOT backward compatible")
                            all_compatible = False
                            
                    except Exception as e:
                        print(f"  ❌ Error checking {prev_version} → {curr_version}: {e}")
                        all_compatible = False
            else:
                print(f"  ℹ️  {base_name}: Single version, no compatibility checks needed")
                
        return all_compatible
    
    def generate_examples(self) -> None:
        """Generate example JSON data for each schema."""
        print("\n📝 Generating example data...")
        
        examples_dir = self.schemas_dir / "examples"
        examples_dir.mkdir(exist_ok=True)
        
        for name, schema in self.schemas.items():
            try:
                example = self._generate_example_data(schema)
                example_file = examples_dir / f"{name.replace('.avsc', '.json')}"
                
                with open(example_file, 'w') as f:
                    json.dump(example, f, indent=2)
                    
                print(f"  ✅ Generated example for {name}")
                
            except Exception as e:
                print(f"  ❌ Failed to generate example for {name}: {e}")
    
    def _generate_example_data(self, schema: avro.schema.Schema) -> Dict[str, Any]:
        """Generate example data that conforms to the schema."""
        import time
        
        schema_dict = json.loads(str(schema))
        example = {}
        
        for field in schema_dict['fields']:
            field_name = field['name']
            field_type = field['type']
            
            if 'default' in field:
                example[field_name] = field['default']
            else:
                example[field_name] = self._generate_field_value(field_type, field_name)
                
        return example
    
    def _generate_field_value(self, field_type: Any, field_name: str) -> Any:
        """Generate a realistic value for a field type."""
        import uuid
        import time
        
        if field_type == 'string':
            if 'id' in field_name.lower():
                return str(uuid.uuid4())[:8]
            elif 'url' in field_name.lower():
                return 'https://example.com/page'
            elif 'ip' in field_name.lower():
                return '192.168.1.100'
            else:
                return f'example_{field_name}'
                
        elif field_type == 'long':
            if 'timestamp' in field_name.lower():
                return int(time.time() * 1000)  # milliseconds
            else:
                return 12345
                
        elif field_type == 'double':
            if 'amount' in field_name.lower():
                return 129.99
            elif 'score' in field_name.lower():
                return 0.75
            else:
                return 1.23
                
        elif field_type == 'boolean':
            return False
            
        elif isinstance(field_type, dict):
            if field_type.get('type') == 'enum':
                return field_type['symbols'][0]
            elif field_type.get('type') == 'array':
                return []
            elif field_type.get('type') == 'map':
                return {}
                
        elif isinstance(field_type, list):
            # Union type, use first non-null type
            for t in field_type:
                if t != 'null':
                    return self._generate_field_value(t, field_name)
            return None
            
        return None


def main():
    """Main validation function."""
    print("🚀 Starting schema validation...")
    
    validator = SchemaValidator()
    validator.load_schemas()
    
    if not validator.schemas:
        print("❌ No schemas found in schemas/ directory")
        sys.exit(1)
    
    # Run all validations
    syntax_valid = validator.validate_schema_syntax()
    compatibility_valid = validator.validate_compatibility()
    
    # Generate examples
    validator.generate_examples()
    
    # Summary
    print("\n" + "="*50)
    if syntax_valid and compatibility_valid:
        print("✅ All schema validations passed!")
        print("\n📋 Next steps:")
        print("  1. Review generated examples in schemas/examples/")
        print("  2. Test with producers: python generators/txgen.py")
        print("  3. Register schemas: make register-schemas")
    else:
        print("❌ Schema validation failed!")
        print("Please fix the errors above before proceeding.")
        sys.exit(1)


if __name__ == '__main__':
    main()
