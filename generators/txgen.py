#!/usr/bin/env python3
"""
Transaction Event Generator

Generates realistic synthetic payment transaction events for fraud detection.
Features:
- Realistic transaction patterns (amounts, merchants, geography)
- Configurable fraud injection
- Device and user session consistency
- Geo-location based on IP addresses
"""

import os
import sys
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
import logging

import click
from faker import Faker
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generators.base_generator import BaseEventGenerator, TimestampMixin, session_manager

logger = logging.getLogger(__name__)


class TransactionGenerator(BaseEventGenerator, TimestampMixin):
    """Generates realistic transaction events with fraud patterns."""
    
    def __init__(self, **kwargs):
        # Extract fraud injection rate
        self.fraud_rate = kwargs.pop('fraud_rate', 0.02)  # 2% fraud rate
        
        super().__init__(
            topic="txn.events",
            schema_file="schemas/transactions.v1.avsc",
            **kwargs
        )
        
        self.fake = Faker()
        Faker.seed(42)  # Reproducible fake data
        
        # Merchant categories and their spending patterns
        self.merchant_categories = {
            'grocery': {'mcc': '5411', 'avg_amount': 85.0, 'std_amount': 30.0, 'fraud_likelihood': 0.05},
            'gas_station': {'mcc': '5542', 'avg_amount': 65.0, 'std_amount': 25.0, 'fraud_likelihood': 0.1},
            'restaurant': {'mcc': '5812', 'avg_amount': 45.0, 'std_amount': 20.0, 'fraud_likelihood': 0.05},
            'retail': {'mcc': '5311', 'avg_amount': 120.0, 'std_amount': 80.0, 'fraud_likelihood': 0.15},
            'online': {'mcc': '5967', 'avg_amount': 75.0, 'std_amount': 40.0, 'fraud_likelihood': 0.8},  # High fraud rate
            'hotel': {'mcc': '7011', 'avg_amount': 180.0, 'std_amount': 90.0, 'fraud_likelihood': 0.6},  # High fraud rate
            'airline': {'mcc': '4511', 'avg_amount': 350.0, 'std_amount': 200.0, 'fraud_likelihood': 0.3},
            'atm': {'mcc': '6011', 'avg_amount': 100.0, 'std_amount': 50.0, 'fraud_likelihood': 0.9},  # Very high fraud rate
            'crypto': {'mcc': '7995', 'avg_amount': 500.0, 'std_amount': 300.0, 'fraud_likelihood': 0.95},  # New high-risk category
            'gambling': {'mcc': '7995', 'avg_amount': 200.0, 'std_amount': 150.0, 'fraud_likelihood': 0.85}  # New high-risk category
        }
        
        # IP address pools for different regions
        self.ip_ranges = {
            'US': ['192.168.', '10.0.', '172.16.'],
            'EU': ['185.', '188.', '195.'],
            'APAC': ['203.', '210.', '218.'],
            'FRAUD': ['tor_exit_', 'proxy_', 'vpn_']  # Suspicious IPs
        }
        
        # Countries and their characteristics
        self.countries = {
            'US': {'fraud_multiplier': 1.0, 'cities': ['New York', 'Los Angeles', 'Chicago', 'Houston']},
            'GB': {'fraud_multiplier': 0.8, 'cities': ['London', 'Manchester', 'Birmingham', 'Leeds']},
            'CA': {'fraud_multiplier': 0.6, 'cities': ['Toronto', 'Vancouver', 'Montreal', 'Calgary']},
            'FR': {'fraud_multiplier': 0.7, 'cities': ['Paris', 'Lyon', 'Marseille', 'Toulouse']},
            'DE': {'fraud_multiplier': 0.5, 'cities': ['Berlin', 'Hamburg', 'Munich', 'Cologne']},
            'CN': {'fraud_multiplier': 5.0, 'cities': ['Beijing', 'Shanghai', 'Guangzhou', 'Shenzhen']},  # Much higher fraud rate
            'RU': {'fraud_multiplier': 8.0, 'cities': ['Moscow', 'St Petersburg', 'Novosibirsk', 'Yekaterinburg']},  # Much higher fraud rate
            'NG': {'fraud_multiplier': 10.0, 'cities': ['Lagos', 'Abuja', 'Kano', 'Ibadan']},  # Very high fraud rate
            'BR': {'fraud_multiplier': 6.0, 'cities': ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador']}  # High fraud rate
        }
        
        # Card ID pool for consistency
        self.card_ids = [f"card_{i:08d}" for i in range(1000, 50000)]
        
        logger.info(f"Initialized TransactionGenerator with {len(self.card_ids)} cards")
        logger.info(f"Fraud injection rate: {self.fraud_rate:.2%}")
        
    def generate_event(self) -> Dict[str, Any]:
        """Generate a single transaction event."""
        # Get user session for consistency
        session = session_manager.get_user_session()
        
        # Decide if this should be a fraud transaction
        is_fraud = random.random() < self.fraud_rate
        
        # Select merchant category
        if is_fraud:
            # Fraudulent transactions more likely in high-risk categories
            weights = [cat['fraud_likelihood'] for cat in self.merchant_categories.values()]
            category = random.choices(list(self.merchant_categories.keys()), weights=weights)[0]
        else:
            category = random.choice(list(self.merchant_categories.keys()))
            
        category_info = self.merchant_categories[category]
        
        # Generate transaction amount
        amount = self._generate_amount(category_info, is_fraud)
        
        # Select card ID (fraudulent transactions use compromised cards more often)
        if is_fraud:
            if random.random() < 0.7:  # 70% of fraud uses "hot" cards
                card_id = random.choice(self.card_ids[:50])  # Top 50 cards are "hot"
            else:  # 30% use brand new cards (card testing)
                card_id = f"card_{random.randint(50000, 99999):08d}"  # New card range
        else:
            card_id = random.choice(self.card_ids[100:])  # Normal cards avoid hot range
            
        # Generate geography
        geo_info = self._generate_geography(is_fraud)
        
        # Create transaction
        event = {
            'txn_id': f"txn_{uuid.uuid4().hex[:12]}",
            'card_id': card_id,
            'user_id': session['user_id'],
            'amount': round(amount, 2),
            'currency': self._select_currency(geo_info['country']),
            'mcc': category_info['mcc'],
            'device_id': session['device_id'],
            'ip_address': geo_info['ip_address'],
            'geo_country': geo_info['country'],
            'geo_city': geo_info['city'],
            'geo_lat': geo_info.get('lat'),
            'geo_lon': geo_info.get('lon'),
            'timestamp': self.current_timestamp_ms(),
            'processing_time': None,  # Will be set by producer
            'is_fraud': is_fraud,  # Store ground truth fraud label
            'metadata': self._generate_metadata(is_fraud, category)
        }
        
        return event
        
    def _generate_amount(self, category_info: Dict, is_fraud: bool) -> float:
        """Generate transaction amount based on category and fraud status."""
        base_amount = np.random.normal(
            category_info['avg_amount'],
            category_info['std_amount']
        )
        
        # Ensure positive amount
        amount = max(1.0, base_amount)
        
        # Make fraud transactions much more obvious
        if is_fraud:
            fraud_type = random.random()
            if fraud_type < 0.4:  # 40% are very small test transactions
                amount = random.uniform(0.01, 1.0)  # Very small amounts
            elif fraud_type < 0.7:  # 30% are extremely large transactions
                amount = random.uniform(5000.0, 50000.0)  # Very large amounts
            elif fraud_type < 0.85:  # 15% are round numbers (suspicious)
                amount = random.choice([100.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0])
            else:  # 15% are just above typical limits
                amount = random.uniform(2000.0, 5000.0)
                
        return amount
        
    def _generate_geography(self, is_fraud: bool) -> Dict[str, Any]:
        """Generate geographic information for the transaction."""
        if is_fraud:
            # Make fraud geography much more obvious
            fraud_geo_type = random.random()
            if fraud_geo_type < 0.6:  # 60% from high-risk countries
                country = random.choice(['CN', 'RU', 'NG', 'BR'])  # High fraud countries
                ip_prefix = random.choice(self.ip_ranges['FRAUD'])
                ip_address = f"{ip_prefix}{random.randint(1, 254)}"
            elif fraud_geo_type < 0.8:  # 20% from suspicious IPs
                country = random.choice(['US', 'GB'])  # Normal country but suspicious IP
                ip_prefix = random.choice(self.ip_ranges['FRAUD'])
                ip_address = f"{ip_prefix}{random.randint(1, 254)}"
            else:  # 20% from very distant locations
                country = random.choice(['CN', 'RU', 'NG'])
                if country in ['US', 'CA']:
                    region = 'US'
                elif country in ['GB', 'FR', 'DE']:
                    region = 'EU'
                else:
                    region = 'APAC'
                ip_prefix = random.choice(self.ip_ranges[region])
                ip_address = f"{ip_prefix}{random.randint(1, 254)}.{random.randint(1, 254)}"
        else:
            # Normal geographic distribution (mostly safe countries)
            safe_countries = ['US', 'GB', 'CA', 'FR', 'DE']
            country_weights = [1.0 / self.countries[c]['fraud_multiplier'] for c in safe_countries]
            country = random.choices(safe_countries, weights=country_weights)[0]
            
            # Select IP range based on country
            if country in ['US', 'CA']:
                region = 'US'
            elif country in ['GB', 'FR', 'DE']:
                region = 'EU'
            else:
                region = 'APAC'
                
            ip_prefix = random.choice(self.ip_ranges[region])
            ip_address = f"{ip_prefix}{random.randint(1, 254)}.{random.randint(1, 254)}"
            
        city = random.choice(self.countries[country]['cities'])
        
        # Generate approximate coordinates for the city
        lat, lon = self._get_city_coordinates(city)
        
        return {
            'country': country,
            'city': city,
            'ip_address': ip_address,
            'lat': lat,
            'lon': lon
        }
        
    def _get_city_coordinates(self, city: str) -> tuple:
        """Get approximate coordinates for a city."""
        # Simplified coordinate lookup
        coords = {
            'New York': (40.7128, -74.0060),
            'Los Angeles': (34.0522, -118.2437),
            'London': (51.5074, -0.1278),
            'Paris': (48.8566, 2.3522),
            'Tokyo': (35.6762, 139.6503),
            'Beijing': (39.9042, 116.4074),
            'Moscow': (55.7558, 37.6173)
        }
        
        if city in coords:
            lat, lon = coords[city]
            # Add some random variation
            lat += random.uniform(-0.1, 0.1)
            lon += random.uniform(-0.1, 0.1)
            return round(lat, 4), round(lon, 4)
        else:
            # Random coordinates if city not found
            return round(random.uniform(-90, 90), 4), round(random.uniform(-180, 180), 4)
            
    def _select_currency(self, country: str) -> str:
        """Select currency based on country."""
        currency_map = {
            'US': 'USD', 'CA': 'CAD', 'GB': 'GBP',
            'FR': 'EUR', 'DE': 'EUR',
            'CN': 'USD', 'RU': 'USD'  # Fraudulent transactions often in USD
        }
        return currency_map.get(country, 'USD')
        
    def _generate_metadata(self, is_fraud: bool, category: str) -> Dict[str, str]:
        """Generate additional metadata for the transaction."""
        if is_fraud:
            # Make fraud metadata very obvious
            metadata = {
                'channel': random.choice(['online', 'atm']),  # Higher risk channels
                'merchant_category': category,
                'risk_flags': random.choice([
                    'velocity_high', 'geo_mismatch', 'device_new', 'amount_unusual',
                    'suspicious_ip', 'high_risk_country', 'round_amount', 'test_transaction'
                ]),
                'device_fingerprint': f"suspicious_device_{random.randint(1000, 9999)}",
                'browser_fingerprint': f"fraud_browser_{random.randint(100, 999)}",
                'merchant_name': random.choice([
                    'SUSPICIOUS_MERCHANT', 'FRAUD_TEST_SITE', 'HIGH_RISK_VENDOR',
                    'CRYPTO_EXCHANGE', 'GAMBLING_SITE', 'UNKNOWN_MERCHANT'
                ])
            }
        else:
            # Normal metadata
            metadata = {
                'channel': random.choice(['online', 'pos', 'atm', 'mobile']),
                'merchant_category': category,
                'device_fingerprint': f"normal_device_{random.randint(10000, 99999)}",
                'browser_fingerprint': f"normal_browser_{random.randint(1000, 9999)}",
                'merchant_name': random.choice([
                    'WALMART', 'TARGET', 'AMAZON', 'STARBUCKS', 'MCDONALDS',
                    'SHELL', 'EXXON', 'HILTON', 'MARRIOTT', 'UNITED_AIRLINES'
                ])
            }
            
        return metadata
        
    def get_partition_key(self, event: Dict[str, Any]) -> str:
        """Use card_id as partition key for fraud detection locality."""
        return event['card_id']


@click.command()
@click.option('--events-per-second', '-r', default=10.0, help='Events per second to generate')
@click.option('--duration', '-d', default=None, type=int, help='Duration in seconds (infinite if not set)')
@click.option('--fraud-rate', '-f', default=0.02, help='Fraud injection rate (0.0-1.0)')
@click.option('--bootstrap-servers', '-b', default='localhost:9092', help='Kafka bootstrap servers')
@click.option('--batch-size', default=100, help='Producer batch size')
@click.option('--metrics-port', default=None, type=int, help='Port for metrics server (optional)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging')
def main(events_per_second, duration, fraud_rate, bootstrap_servers, batch_size, metrics_port, verbose):
    """Transaction event generator for fraud detection."""
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    try:
        generator = TransactionGenerator(
            events_per_second=events_per_second,
            duration_seconds=duration,
            fraud_rate=fraud_rate,
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
