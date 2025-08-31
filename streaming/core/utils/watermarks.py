#!/usr/bin/env python3
"""
Watermark and event-time utilities for Flink streaming jobs.

This module provides utilities for:
- Event-time extraction
- Watermark generation strategies  
- Late event handling
- Out-of-order event detection
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass


@dataclass
class WatermarkConfig:
    """Configuration for watermark generation."""
    max_out_of_orderness_ms: int = 5000  # 5 seconds
    allowed_lateness_ms: int = 60000      # 1 minute
    idle_source_timeout_ms: int = 300000  # 5 minutes


class EventTimeExtractor:
    """Extract event timestamps from streaming events."""
    
    @staticmethod
    def extract_timestamp(event: Dict[str, Any], timestamp_field: str = 'timestamp') -> int:
        """
        Extract timestamp from event.
        
        Args:
            event: Event dictionary
            timestamp_field: Field name containing timestamp
            
        Returns:
            Timestamp in milliseconds since epoch
        """
        timestamp = event.get(timestamp_field)
        
        if timestamp is None:
            # Fallback to current time
            return int(time.time() * 1000)
            
        # Handle different timestamp formats
        if isinstance(timestamp, str):
            try:
                # Try parsing ISO format
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            except ValueError:
                # Try parsing as unix timestamp string
                return int(float(timestamp) * 1000)
        elif isinstance(timestamp, (int, float)):
            # Assume milliseconds if > 1e10, else seconds
            if timestamp > 1e10:
                return int(timestamp)
            else:
                return int(timestamp * 1000)
        else:
            # Fallback to current time
            return int(time.time() * 1000)


class WatermarkGenerator:
    """Generate watermarks for event-time processing."""
    
    def __init__(self, config: WatermarkConfig):
        self.config = config
        self.last_emitted_watermark = 0
        self.max_seen_timestamp = 0
        
    def generate_watermark(self, event_timestamp: int) -> Optional[int]:
        """
        Generate watermark based on event timestamp.
        
        Args:
            event_timestamp: Event timestamp in milliseconds
            
        Returns:
            Watermark timestamp or None if no watermark should be emitted
        """
        # Update max seen timestamp
        self.max_seen_timestamp = max(self.max_seen_timestamp, event_timestamp)
        
        # Calculate watermark (max_timestamp - allowable_delay)
        watermark = self.max_seen_timestamp - self.config.max_out_of_orderness_ms
        
        # Only emit if watermark has advanced
        if watermark > self.last_emitted_watermark:
            self.last_emitted_watermark = watermark
            return watermark
            
        return None
    
    def get_current_watermark(self) -> int:
        """Get the current watermark value."""
        return self.last_emitted_watermark
    
    def is_late_event(self, event_timestamp: int) -> bool:
        """Check if an event is late (arrives after watermark + allowed lateness)."""
        cutoff = self.last_emitted_watermark + self.config.allowed_lateness_ms
        return event_timestamp < cutoff


class OutOfOrderDetector:
    """Detect and analyze out-of-order events."""
    
    def __init__(self, window_size_ms: int = 60000):
        self.window_size_ms = window_size_ms
        self.timestamps = []
        self.out_of_order_count = 0
        self.total_events = 0
        
    def process_event(self, timestamp: int) -> Dict[str, Any]:
        """
        Process an event and detect if it's out of order.
        
        Args:
            timestamp: Event timestamp in milliseconds
            
        Returns:
            Analysis results
        """
        self.total_events += 1
        
        # Check if out of order
        is_out_of_order = False
        if self.timestamps and timestamp < self.timestamps[-1]:
            is_out_of_order = True
            self.out_of_order_count += 1
            
        # Maintain sliding window of timestamps
        self.timestamps.append(timestamp)
        current_time = int(time.time() * 1000)
        cutoff_time = current_time - self.window_size_ms
        
        # Remove old timestamps
        self.timestamps = [ts for ts in self.timestamps if ts > cutoff_time]
        
        return {
            'is_out_of_order': is_out_of_order,
            'out_of_order_rate': self.out_of_order_count / max(self.total_events, 1),
            'window_events': len(self.timestamps),
            'max_delay_ms': max(0, current_time - min(self.timestamps)) if self.timestamps else 0
        }


class LateEventHandler:
    """Handle late events that arrive after watermarks."""
    
    def __init__(self, config: WatermarkConfig):
        self.config = config
        self.late_events_count = 0
        self.late_events_buffer = []
        
    def handle_late_event(self, event: Dict[str, Any], event_timestamp: int, watermark: int) -> str:
        """
        Handle a late event.
        
        Args:
            event: The late event
            event_timestamp: Event timestamp
            watermark: Current watermark
            
        Returns:
            Action taken ('dropped', 'buffered', 'processed')
        """
        self.late_events_count += 1
        
        # Calculate how late the event is
        lateness_ms = watermark - event_timestamp
        
        if lateness_ms > self.config.allowed_lateness_ms:
            # Event is too late, drop it
            return 'dropped'
        else:
            # Event is late but within allowed lateness, buffer it
            self.late_events_buffer.append({
                'event': event,
                'timestamp': event_timestamp,
                'lateness_ms': lateness_ms,
                'received_at': int(time.time() * 1000)
            })
            return 'buffered'
    
    def get_buffered_events(self, before_timestamp: int = None) -> list:
        """Get buffered late events, optionally filtered by timestamp."""
        if before_timestamp is None:
            return self.late_events_buffer.copy()
        else:
            return [e for e in self.late_events_buffer if e['timestamp'] < before_timestamp]
    
    def clear_buffer(self, before_timestamp: int = None):
        """Clear buffered events, optionally keeping events after timestamp."""
        if before_timestamp is None:
            self.late_events_buffer.clear()
        else:
            self.late_events_buffer = [e for e in self.late_events_buffer if e['timestamp'] >= before_timestamp]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get late event statistics."""
        return {
            'total_late_events': self.late_events_count,
            'buffered_events': len(self.late_events_buffer),
            'avg_lateness_ms': sum(e['lateness_ms'] for e in self.late_events_buffer) / max(len(self.late_events_buffer), 1)
        }


def create_periodic_watermark_generator(interval_ms: int = 1000) -> Callable:
    """
    Create a periodic watermark generator function.
    
    Args:
        interval_ms: Interval between watermark emissions
        
    Returns:
        Function that generates periodic watermarks
    """
    last_watermark_time = 0
    
    def generate_periodic_watermark():
        nonlocal last_watermark_time
        current_time = int(time.time() * 1000)
        
        if current_time - last_watermark_time >= interval_ms:
            last_watermark_time = current_time
            return current_time - 5000  # 5 second delay
        return None
    
    return generate_periodic_watermark


# Example usage and testing
if __name__ == '__main__':
    import random
    
    print("🧪 Testing Watermark Utilities")
    
    # Test watermark generation
    config = WatermarkConfig(max_out_of_orderness_ms=2000)
    watermark_gen = WatermarkGenerator(config)
    
    # Simulate events
    base_time = int(time.time() * 1000)
    events = []
    
    for i in range(10):
        # Add some out-of-order events
        timestamp = base_time + (i * 1000) + random.randint(-500, 500)
        events.append(timestamp)
    
    print(f"Processing {len(events)} events...")
    
    for i, timestamp in enumerate(events):
        watermark = watermark_gen.generate_watermark(timestamp)
        is_late = watermark_gen.is_late_event(timestamp)
        
        print(f"Event {i}: ts={timestamp}, watermark={watermark}, late={is_late}")
    
    # Test out-of-order detection
    detector = OutOfOrderDetector()
    
    print("\n🔍 Out-of-order Analysis:")
    for timestamp in sorted(events)[::2] + sorted(events)[1::2]:  # Mix order
        analysis = detector.process_event(timestamp)
        if analysis['is_out_of_order']:
            print(f"Out-of-order event: ts={timestamp}, rate={analysis['out_of_order_rate']:.2%}")
    
    print(f"Final out-of-order rate: {analysis['out_of_order_rate']:.2%}")
    print("✅ Watermark utilities test completed")
