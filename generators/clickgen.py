#!/usr/bin/env python3
"""
Clickstream Event Generator

Generates realistic synthetic user clickstream events for personalization.
Features:
- User session management with realistic browsing patterns
- Product catalog simulation
- Purchase funnel modeling
- Referrer and navigation flow simulation
"""

import os
import sys
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import logging

import click
from faker import Faker
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generators.base_generator import BaseEventGenerator, TimestampMixin, session_manager

logger = logging.getLogger(__name__)


class ClickstreamGenerator(BaseEventGenerator, TimestampMixin):
    """Generates realistic clickstream events for personalization."""
    
    def __init__(self, **kwargs):
        super().__init__(
            topic="click.events", 
            schema_file="schemas/clicks.v1.avsc",
            **kwargs
        )
        
        self.fake = Faker()
        Faker.seed(43)  # Different seed from transaction generator
        
        # Product catalog
        self.categories = {
            'electronics': {
                'items': ['laptop', 'smartphone', 'tablet', 'headphones', 'camera'],
                'price_range': (50, 2000),
                'conversion_rate': 0.03
            },
            'clothing': {
                'items': ['shirt', 'jeans', 'dress', 'shoes', 'jacket'],
                'price_range': (20, 300),
                'conversion_rate': 0.08
            },
            'books': {
                'items': ['novel', 'textbook', 'cookbook', 'biography', 'magazine'],
                'price_range': (10, 100),
                'conversion_rate': 0.12
            },
            'home': {
                'items': ['furniture', 'decor', 'kitchen', 'bedding', 'lighting'],
                'price_range': (25, 1000),
                'conversion_rate': 0.05
            },
            'sports': {
                'items': ['equipment', 'apparel', 'shoes', 'accessories', 'supplements'],
                'price_range': (15, 500),
                'conversion_rate': 0.06
            }
        }
        
        # Generate product catalog
        self.products = self._generate_product_catalog()
        
        # Page types and their transition probabilities
        self.page_transitions = {
            'HOME': {
                'CATEGORY': 0.4,
                'PRODUCT': 0.3,
                'CART': 0.1,
                'PROFILE': 0.1,
                'OTHER': 0.1
            },
            'CATEGORY': {
                'PRODUCT': 0.6,
                'CATEGORY': 0.2,
                'HOME': 0.1,
                'CART': 0.05,
                'OTHER': 0.05
            },
            'PRODUCT': {
                'CART': 0.3,
                'PRODUCT': 0.3,
                'CATEGORY': 0.2,
                'HOME': 0.1,
                'CHECKOUT': 0.1
            },
            'CART': {
                'CHECKOUT': 0.4,
                'PRODUCT': 0.3,
                'HOME': 0.2,
                'CATEGORY': 0.1
            },
            'CHECKOUT': {
                'HOME': 0.7,
                'PRODUCT': 0.2,
                'PROFILE': 0.1
            },
            'PROFILE': {
                'HOME': 0.5,
                'PRODUCT': 0.3,
                'OTHER': 0.2
            }
        }
        
        # Action types and their probabilities per page type
        self.action_probabilities = {
            'HOME': {'VIEW': 0.8, 'CLICK': 0.2},
            'CATEGORY': {'VIEW': 0.6, 'CLICK': 0.3, 'SEARCH': 0.1},
            'PRODUCT': {'VIEW': 0.4, 'CLICK': 0.3, 'ADD_TO_CART': 0.2, 'PURCHASE': 0.1},
            'CART': {'VIEW': 0.4, 'CLICK': 0.2, 'REMOVE_FROM_CART': 0.2, 'PURCHASE': 0.2},
            'CHECKOUT': {'VIEW': 0.3, 'CLICK': 0.3, 'PURCHASE': 0.4},
            'PROFILE': {'VIEW': 0.7, 'CLICK': 0.3}
        }
        
        # User browsing patterns (session state)
        self.user_sessions = {}
        
        # Referrer sources
        self.referrers = {
            'direct': 0.4,
            'google.com': 0.25,
            'facebook.com': 0.15,
            'twitter.com': 0.1,
            'instagram.com': 0.05,
            'youtube.com': 0.05
        }
        
        # User agents for different devices
        self.user_agents = {
            'desktop': [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ],
            'mobile': [
                'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15',
                'Mozilla/5.0 (Android 11; Mobile; rv:68.0) Gecko/68.0 Firefox/88.0'
            ],
            'tablet': [
                'Mozilla/5.0 (iPad; CPU OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15'
            ]
        }
        
        logger.info(f"Initialized ClickstreamGenerator with {len(self.products)} products")
        
    def _generate_product_catalog(self) -> List[Dict[str, Any]]:
        """Generate a synthetic product catalog."""
        products = []
        product_id = 1
        
        for category, info in self.categories.items():
            for item_type in info['items']:
                for i in range(20):  # 20 products per item type
                    price = random.uniform(*info['price_range'])
                    products.append({
                        'id': f"prod_{product_id:06d}",
                        'name': f"{item_type.title()} {i+1}",
                        'category': category,
                        'price': round(price, 2),
                        'rating': round(random.uniform(2.0, 5.0), 1),
                        'reviews': random.randint(0, 1000)
                    })
                    product_id += 1
                    
        return products
        
    def generate_event(self) -> Dict[str, Any]:
        """Generate a single clickstream event."""
        # Get user session
        session_info = session_manager.get_user_session()
        user_id = session_info['user_id']
        session_id = session_info['session_id']
        device_id = session_info['device_id']
        
        # Get or create user session state
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = self._create_user_session()
            
        user_session = self.user_sessions[user_id]
        
        # Determine next page based on current page and transition probabilities
        current_page = user_session.get('current_page', 'HOME')
        next_page = self._get_next_page(current_page)
        
        # Generate page URL
        page_url = self._generate_page_url(next_page, user_session)
        
        # Select action based on page type
        action_type = self._select_action(next_page)
        
        # Get product/item info if relevant
        item_info = self._get_item_info(next_page, action_type, user_session)
        
        # Update user session state
        self._update_user_session(user_session, next_page, action_type, item_info)
        
        # Generate dwell time (time spent on previous page)
        dwell_time = self._calculate_dwell_time(current_page, next_page)
        
        # Select device characteristics
        device_type = random.choices(['desktop', 'mobile', 'tablet'], weights=[0.5, 0.4, 0.1])[0]
        user_agent = random.choice(self.user_agents[device_type])
        
        # Create event
        event = {
            'event_id': f"click_{uuid.uuid4().hex[:12]}",
            'user_id': user_id,
            'session_id': session_id,
            'page_url': page_url,
            'page_type': next_page,
            'item_id': item_info.get('item_id'),
            'category_id': item_info.get('category_id'),
            'action_type': action_type,
            'referrer_url': user_session.get('previous_url'),
            'device_id': device_id,
            'user_agent': user_agent,
            'ip_address': self._generate_ip_address(),
            'dwell_time_ms': dwell_time,
            'scroll_depth': self._generate_scroll_depth(next_page, action_type),
            'timestamp': self.current_timestamp_ms(),
            'processing_time': None,
            'experiment_ids': self._get_experiment_ids(),
            'metadata': self._generate_metadata(next_page, action_type, device_type)
        }
        
        return event
        
    def _create_user_session(self) -> Dict[str, Any]:
        """Create initial user session state."""
        return {
            'current_page': 'HOME',
            'previous_url': self._select_referrer(),
            'cart_items': [],
            'viewed_products': [],
            'categories_browsed': set(),
            'session_start': self.current_timestamp_ms()
        }
        
    def _get_next_page(self, current_page: str) -> str:
        """Determine next page based on transition probabilities."""
        if current_page not in self.page_transitions:
            return 'HOME'
            
        transitions = self.page_transitions[current_page]
        pages = list(transitions.keys())
        weights = list(transitions.values())
        
        return random.choices(pages, weights=weights)[0]
        
    def _generate_page_url(self, page_type: str, user_session: Dict) -> str:
        """Generate realistic page URL based on page type."""
        base_url = "https://ecommerce-demo.com"
        
        if page_type == 'HOME':
            return f"{base_url}/"
        elif page_type == 'CATEGORY':
            category = random.choice(list(self.categories.keys()))
            return f"{base_url}/category/{category}"
        elif page_type == 'PRODUCT':
            product = random.choice(self.products)
            return f"{base_url}/product/{product['id']}"
        elif page_type == 'CART':
            return f"{base_url}/cart"
        elif page_type == 'CHECKOUT':
            return f"{base_url}/checkout"
        elif page_type == 'PROFILE':
            return f"{base_url}/profile"
        else:
            return f"{base_url}/other"
            
    def _select_action(self, page_type: str) -> str:
        """Select action based on page type probabilities."""
        if page_type not in self.action_probabilities:
            return 'VIEW'
            
        actions = self.action_probabilities[page_type]
        action_types = list(actions.keys())
        weights = list(actions.values())
        
        return random.choices(action_types, weights=weights)[0]
        
    def _get_item_info(self, page_type: str, action_type: str, user_session: Dict) -> Dict[str, Any]:
        """Get item/product information if relevant for the action."""
        info = {}
        
        if page_type in ['PRODUCT', 'CART'] or action_type in ['ADD_TO_CART', 'REMOVE_FROM_CART', 'PURCHASE']:
            if page_type == 'CART' and user_session['cart_items']:
                # Select from cart items
                product = random.choice(user_session['cart_items'])
            else:
                # Select random product
                product = random.choice(self.products)
                
            info['item_id'] = product['id']
            info['category_id'] = product['category']
            
        elif page_type == 'CATEGORY':
            category = random.choice(list(self.categories.keys()))
            info['category_id'] = category
            
        return info
        
    def _update_user_session(self, user_session: Dict, page_type: str, action_type: str, item_info: Dict):
        """Update user session state based on action."""
        user_session['current_page'] = page_type
        
        if action_type == 'ADD_TO_CART' and 'item_id' in item_info:
            product = next(p for p in self.products if p['id'] == item_info['item_id'])
            if product not in user_session['cart_items']:
                user_session['cart_items'].append(product)
                
        elif action_type == 'REMOVE_FROM_CART' and 'item_id' in item_info:
            user_session['cart_items'] = [
                p for p in user_session['cart_items'] 
                if p['id'] != item_info['item_id']
            ]
            
        elif action_type == 'PURCHASE':
            user_session['cart_items'] = []  # Clear cart after purchase
            
        if page_type == 'PRODUCT' and 'item_id' in item_info:
            if item_info['item_id'] not in user_session['viewed_products']:
                user_session['viewed_products'].append(item_info['item_id'])
                
        if 'category_id' in item_info:
            user_session['categories_browsed'].add(item_info['category_id'])
            
    def _calculate_dwell_time(self, current_page: str, next_page: str) -> Optional[int]:
        """Calculate time spent on previous page."""
        if current_page == 'HOME':
            return None  # First page of session
            
        # Base dwell times by page type (in milliseconds)
        base_times = {
            'HOME': 15000,
            'CATEGORY': 25000, 
            'PRODUCT': 45000,
            'CART': 20000,
            'CHECKOUT': 60000,
            'PROFILE': 30000
        }
        
        base_time = base_times.get(current_page, 20000)
        
        # Add some randomness (log-normal distribution)
        multiplier = np.random.lognormal(0, 0.5)
        dwell_time = int(base_time * multiplier)
        
        # Cap at reasonable limits
        return max(1000, min(300000, dwell_time))  # 1s to 5min
        
    def _generate_scroll_depth(self, page_type: str, action_type: str) -> Optional[float]:
        """Generate scroll depth for the page."""
        if page_type in ['CHECKOUT', 'CART']:
            # Higher scroll depth for functional pages
            return round(random.uniform(0.7, 1.0), 2)
        elif page_type == 'PRODUCT':
            # Product pages often scrolled to see details
            return round(random.uniform(0.3, 0.9), 2)
        elif action_type == 'VIEW':
            # Quick views have lower scroll
            return round(random.uniform(0.1, 0.4), 2)
        else:
            return round(random.uniform(0.2, 0.8), 2)
            
    def _generate_ip_address(self) -> str:
        """Generate a realistic IP address."""
        # Simple IP generation
        return f"{random.randint(1, 223)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
        
    def _select_referrer(self) -> str:
        """Select referrer source."""
        referrers = list(self.referrers.keys())
        weights = list(self.referrers.values())
        source = random.choices(referrers, weights=weights)[0]
        
        if source == 'direct':
            return None
        else:
            return f"https://{source}/search?q=products"
            
    def _get_experiment_ids(self) -> List[str]:
        """Get A/B test experiment IDs."""
        # 50% chance of being in an experiment
        if random.random() < 0.5:
            experiments = ['rec_algo_v2', 'checkout_flow_b', 'homepage_layout_test']
            return [random.choice(experiments)]
        return []
        
    def _generate_metadata(self, page_type: str, action_type: str, device_type: str) -> Dict[str, str]:
        """Generate additional metadata."""
        metadata = {
            'device_type': device_type,
            'browser': random.choice(['Chrome', 'Firefox', 'Safari', 'Edge']),
        }
        
        if page_type == 'PRODUCT':
            metadata['product_view_source'] = random.choice(['search', 'category', 'recommendation', 'direct'])
            
        if action_type == 'SEARCH':
            metadata['search_query'] = random.choice(['shoes', 'laptop', 'book', 'gift', 'sale'])
            
        return metadata
        
    def get_partition_key(self, event: Dict[str, Any]) -> str:
        """Use user_id as partition key for personalization locality."""
        return event['user_id']


@click.command()
@click.option('--events-per-second', '-r', default=15.0, help='Events per second to generate')
@click.option('--duration', '-d', default=None, type=int, help='Duration in seconds (infinite if not set)')
@click.option('--bootstrap-servers', '-b', default='localhost:9092', help='Kafka bootstrap servers')
@click.option('--batch-size', default=100, help='Producer batch size')
@click.option('--metrics-port', default=None, type=int, help='Port for metrics server (optional)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging')
def main(events_per_second, duration, bootstrap_servers, batch_size, metrics_port, verbose):
    """Clickstream event generator for personalization."""
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    try:
        generator = ClickstreamGenerator(
            events_per_second=events_per_second,
            duration_seconds=duration,
            bootstrap_servers=bootstrap_servers,
            batch_size=batch_size,
            metrics_port=metrics_port
        )
        
        generator.run()
        
    except Exception as e:
        logger.error(f"Generator failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
