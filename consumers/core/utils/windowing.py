"""
Windowing utilities for stream processing.

Implements sliding window functionality for aggregating time-series data.
"""

from typing import Dict, Any, List
from collections import deque


class SlidingWindow:
    """Sliding window implementation for aggregations."""
    
    def __init__(self, window_size_ms: int, slide_size_ms: int):
        """
        Initialize sliding window.
        
        Args:
            window_size_ms: Window size in milliseconds
            slide_size_ms: How often window slides in milliseconds
        """
        self.window_size_ms = window_size_ms
        self.slide_size_ms = slide_size_ms
        self.events = deque()
        
    def add_event(self, timestamp: int, event: Dict[str, Any]):
        """Add event to window."""
        self.events.append((timestamp, event))
        self._cleanup_old_events(timestamp)
        
    def _cleanup_old_events(self, current_timestamp: int):
        """Remove events outside the window."""
        cutoff = current_timestamp - self.window_size_ms
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()
            
    def get_events(self) -> List[tuple]:
        """Get all events in current window."""
        return list(self.events)
        
    def size(self) -> int:
        """Get number of events in window."""
        return len(self.events)
        
    def get_events_in_range(self, start_timestamp: int, end_timestamp: int) -> List[tuple]:
        """Get events within a specific timestamp range."""
        return [
            (timestamp, event) for timestamp, event in self.events
            if start_timestamp <= timestamp <= end_timestamp
        ]
        
    def clear(self):
        """Clear all events from window."""
        self.events.clear()
