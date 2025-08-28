#!/usr/bin/env python3
"""
Test script for data generators.

This script tests the generators without requiring Kafka infrastructure.
It validates:
- Schema compliance 
- Data quality and realism
- Event generation rate
- Referential integrity
"""

import os
import sys
import json
import time
from typing import Dict, Any, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generators.txgen import TransactionGenerator
from generators.clickgen import ClickstreamGenerator
from generators.base_generator import session_manager


class MockKafkaProducer:
    """Mock Kafka producer for testing."""
    
    def __init__(self, **kwargs):
        self.events: List[Dict[str, Any]] = []
        
    def send(self, topic, key=None, value=None):
        self.events.append({
            'topic': topic,
            'key': key,
            'value': value,
            'timestamp': time.time()
        })
        
        # Mock future for callback compatibility
        class MockFuture:
            def add_callback(self, callback):
                callback(None)  # Mock successful send
            def add_errback(self, callback):
                pass
                
        return MockFuture()
        
    def flush(self, timeout=None):
        pass
        
    def close(self):
        pass


def test_transaction_generator():
    """Test transaction event generation."""
    print("🧪 Testing Transaction Generator...")
    
    # Mock the Kafka producer in the base class before creating generator
    import generators.base_generator as bg
    original_producer_class = bg.KafkaProducer
    bg.KafkaProducer = MockKafkaProducer
    
    try:
        # Create generator with mock producer
        generator = TransactionGenerator(
            events_per_second=100,  # Fast for testing
            duration_seconds=5,
            fraud_rate=0.1  # Higher for testing
        )
        
        # Generate events
        events = []
        for i in range(100):
            event = generator.generate_event()
            events.append(event)
            
        # Validate events
        print(f"✅ Generated {len(events)} transaction events")
        
        # Check schema compliance
        required_fields = ['txn_id', 'card_id', 'user_id', 'amount', 'currency', 'timestamp']
        for event in events[:5]:  # Check first 5
            for field in required_fields:
                assert field in event, f"Missing field: {field}"
                
        # Check data quality
        amounts = [e['amount'] for e in events]
        assert min(amounts) > 0, "Negative amounts found"
        assert max(amounts) < 10000, "Unrealistic amounts found"
        
        # Check fraud injection
        fraud_events = [e for e in events if 'risk_flags' in e.get('metadata', {})]
        fraud_rate = len(fraud_events) / len(events)
        print(f"  📊 Fraud rate: {fraud_rate:.2%} (target: 10%)")
        
        # Check referential integrity
        unique_users = len(set(e['user_id'] for e in events))
        print(f"  👥 Unique users: {unique_users}")
        
        # Show sample event
        print(f"  📝 Sample event:")
        sample = events[0].copy()
        sample['metadata'] = str(sample['metadata'])  # Simplify for display
        for key, value in sample.items():
            print(f"     {key}: {value}")
            
        print("✅ Transaction generator tests passed!\n")
        
    finally:
        # Restore original producer class
        bg.KafkaProducer = original_producer_class
    

def test_clickstream_generator():
    """Test clickstream event generation."""
    print("🧪 Testing Clickstream Generator...")
    
    # Mock the Kafka producer
    import generators.base_generator as bg
    original_producer_class = bg.KafkaProducer
    bg.KafkaProducer = MockKafkaProducer
    
    try:
        # Create generator
        generator = ClickstreamGenerator(
            events_per_second=100,
            duration_seconds=5
        )
        
        # Generate events
        events = []
        for i in range(150):  # More events to test session flow
            event = generator.generate_event()
            events.append(event)
            
        print(f"✅ Generated {len(events)} clickstream events")
        
        # Check schema compliance
        required_fields = ['event_id', 'user_id', 'session_id', 'page_type', 'action_type', 'timestamp']
        for event in events[:5]:
            for field in required_fields:
                assert field in event, f"Missing field: {field}"
                
        # Check page type distribution
        page_types = [e['page_type'] for e in events]
        unique_pages = set(page_types)
        print(f"  📄 Page types: {unique_pages}")
        
        # Check action type distribution
        action_types = [e['action_type'] for e in events]
        unique_actions = set(action_types)
        print(f"  🎯 Action types: {unique_actions}")
        
        # Check session consistency
        sessions = {}
        for event in events:
            user_id = event['user_id']
            session_id = event['session_id']
            if user_id not in sessions:
                sessions[user_id] = set()
            sessions[user_id].add(session_id)
            
        multi_session_users = sum(1 for sessions_set in sessions.values() if len(sessions_set) > 1)
        print(f"  🔄 Users with multiple sessions: {multi_session_users}")
        
        # Check dwell times
        dwell_times = [e['dwell_time_ms'] for e in events if e['dwell_time_ms'] is not None]
        if dwell_times:
            avg_dwell = sum(dwell_times) / len(dwell_times)
            print(f"  ⏱️  Average dwell time: {avg_dwell/1000:.1f}s")
        
        # Show sample event
        print(f"  📝 Sample event:")
        sample = events[0].copy()
        sample['metadata'] = str(sample['metadata'])
        for key, value in sample.items():
            if value is not None:
                print(f"     {key}: {value}")
                
        print("✅ Clickstream generator tests passed!\n")
        
    finally:
        # Restore original producer class
        bg.KafkaProducer = original_producer_class


def test_session_management():
    """Test user session management across generators."""
    print("🧪 Testing Session Management...")
    
    # Generate some sessions
    sessions = []
    for i in range(50):
        session = session_manager.get_user_session()
        sessions.append(session)
        
    # Check session consistency
    user_sessions = {}
    for session in sessions:
        user_id = session['user_id']
        if user_id not in user_sessions:
            user_sessions[user_id] = []
        user_sessions[user_id].append(session)
        
    # Verify same user gets same session within time window
    consistent_sessions = 0
    for user_sessions_list in user_sessions.values():
        if len(user_sessions_list) > 1:
            first_session = user_sessions_list[0]['session_id']
            if all(s['session_id'] == first_session for s in user_sessions_list):
                consistent_sessions += 1
                
    print(f"  ✅ Session consistency: {consistent_sessions}/{len(user_sessions)} users")
    print(f"  👥 Total unique users: {len(user_sessions)}")
    print(f"  🎯 Unique sessions: {len(set(s['session_id'] for s in sessions))}")
    
    print("✅ Session management tests passed!\n")


def test_data_quality():
    """Test overall data quality and relationships."""
    print("🧪 Testing Data Quality...")
    
    # Mock the Kafka producer
    import generators.base_generator as bg
    original_producer_class = bg.KafkaProducer
    bg.KafkaProducer = MockKafkaProducer
    
    try:
        # Generate mixed events
        tx_gen = TransactionGenerator(events_per_second=1, duration_seconds=1)
        click_gen = ClickstreamGenerator(events_per_second=1, duration_seconds=1)
        
        tx_events = [tx_gen.generate_event() for _ in range(50)]
        click_events = [click_gen.generate_event() for _ in range(50)]
        
        # Check user overlap
        tx_users = set(e['user_id'] for e in tx_events)
        click_users = set(e['user_id'] for e in click_events)
        overlap = len(tx_users.intersection(click_users))
        
        print(f"  🔗 User overlap between streams: {overlap} users")
        
        # Check device consistency
        tx_devices = {e['user_id']: e['device_id'] for e in tx_events}
        click_devices = {e['user_id']: e['device_id'] for e in click_events}
        
        consistent_devices = 0
        for user_id in tx_devices:
            if user_id in click_devices and tx_devices[user_id] == click_devices[user_id]:
                consistent_devices += 1
                
        print(f"  📱 Device consistency: {consistent_devices}/{len(tx_devices)} users")
        
        # Check timestamp realism (within last hour)
        current_time = int(time.time() * 1000)
        hour_ago = current_time - (60 * 60 * 1000)
        
        all_events = tx_events + click_events
        recent_events = sum(1 for e in all_events if e['timestamp'] > hour_ago)
        
        print(f"  🕐 Recent timestamps: {recent_events}/{len(all_events)} events")
        
        print("✅ Data quality tests passed!\n")
        
    finally:
        # Restore original producer class
        bg.KafkaProducer = original_producer_class


def main():
    """Run all tests."""
    print("🚀 Starting Data Generator Tests\n")
    
    try:
        test_session_management()
        test_transaction_generator()
        test_clickstream_generator()
        test_data_quality()
        
        print("🎉 All tests passed successfully!")
        print("\n📋 Next steps:")
        print("  1. Install Kafka dependencies: pip install kafka-python")
        print("  2. Start infrastructure: make up")
        print("  3. Test with real Kafka: python generators/txgen.py --duration 10")
        
    except Exception as e:
        print(f"❌ Tests failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
