# Autonomous Generative Trading Strategist

## Objective
A self-evolving AI system that autonomously generates, tests, and implements advanced trading strategies using generative AI and reinforcement learning. It continuously improves by analyzing market data and outcomes, adapting to new conditions without human intervention.

## Strategy
Implement a generative AI model to create novel trading algorithms, integrate reinforcement learning for real-time strategy optimization, and use sentiment analysis for data interpretation. Ensure scalability through cloud-based infrastructure and decentralized operations.

## Execution Output
SUMMARY: Successfully architected and implemented the production-grade Data Fabric Layer for the Autonomous Generative Trading Strategist. Built a multi-modal ingestion engine with robust error handling, Firebase Firestore integration, and comprehensive edge case management. Created 5 core system files that form the foundation for autonomous market perception.

OUTPUT: Created a complete data ingestion pipeline with the following components:

### FILE: config.py
```python
"""
Configuration management for Autonomous Generative Trading Strategist.
Centralized configuration with environment variable fallbacks.
"""
import os
from dataclasses import dataclass
from typing import Optional
import logging

@dataclass
class FirebaseConfig:
    """Firebase configuration"""
    project_id: str = os.getenv('FIREBASE_PROJECT_ID', 'autonomous-trader')
    credentials_path: str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', './firebase-creds.json')
    
@dataclass
class ExchangeConfig:
    """Exchange API configuration"""
    binance_api_key: str = os.getenv('BINANCE_API_KEY', '')
    binance_api_secret: str = os.getenv('BINANCE_API_SECRET', '')
    exchange_rate_limit: int = 10  # requests per second
    websocket_timeout: int = 30  # seconds
    
@dataclass
class APIConfig:
    """Third-party API configuration"""
    etherscan_api_key: str = os.getenv('ETHERSCAN_API_KEY', '')
    fred_api_key: str = os.getenv('FRED_API_KEY', '')
    newsapi_key: str = os.getenv('NEWSAPI_KEY', '')
    
@dataclass
class SystemConfig:
    """System-wide configuration"""
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    data_retention_days: int = 30
    max_retries: int = 3
    retry_delay: int = 5  # seconds
    
class ConfigManager:
    """Singleton configuration manager with validation"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize configuration with validation"""
        self.firebase = FirebaseConfig()
        self.exchange = ExchangeConfig()
        self.api = APIConfig()
        self.system = SystemConfig()
        self._validate_config()
        
    def _validate_config(self):
        """Validate critical configuration parameters"""
        errors = []
        
        # Validate Firebase
        if not os.path.exists(self.firebase.credentials_path):
            errors.append(f"Firebase credentials not found at {self.firebase.credentials_path}")
            
        # Validate required APIs for production
        if not self.exchange.binance_api_key and os.getenv('ENVIRONMENT') == 'production':
            errors.append("Binance API key required for production")
            
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(errors)
            logging.error(error_msg)
            raise ValueError(error_msg)
            
    @staticmethod
    def setup_logging(log_level: str = 'INFO'):
        """Configure structured logging"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('autonomous_trader.log')
            ]
        )
        return logging.getLogger(__name__)
```

### FILE: data_fabric/base_ingester.py
```python
"""
Base ingestion engine with common functionality for all data sources.
Implements retry logic, error handling, and Firebase integration.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
import logging
from datetime import datetime, timedelta
import backoff

import firebase_admin
from firebase_admin import firestore, credentials
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from config import ConfigManager

class BaseIngester(ABC):
    """Abstract base class for all data ingestors"""
    
    def __init__(self, source_name: str, collection_name: str):
        """
        Initialize base ingester
        
        Args:
            source_name: Name of data source for logging
            collection_name: Firestore collection name
        """
        self.config = ConfigManager()
        self.logger = logging.getLogger(f"{__name__}.{source_name}")
        self.source_name = source_name
        self.collection_name = collection_name
        self._firestore_client = None
        self._last_ingestion_time = None
        self._error_count = 0
        self._max_errors_before_alert = 10
        
        # Rate limiting
        self._request_timestamps = []
        self._rate_limit_window = 60  # seconds
        
    @property
    def firestore_client(self):
        """Lazy-loaded Firestore client with singleton pattern"""
        if self._firestore_client is None:
            try:
                # Initialize Firebase if not already initialized
                if not firebase_admin._apps:
                    cred = credentials.Certificate(self.config.firebase.credentials_path)
                    firebase_admin.initialize_app(cred)
                
                self._firestore_client = firestore.client()
                self.logger.info(f"Firestore client initialized for {self.source_name}")
            except Exception as e:
                self.logger.error(f"Failed to initialize Firestore: {str(e)}")
                raise
        return self._firestore_client
    
    def _enforce_rate_limit(self, max_requests: int = 10):
        """Enforce rate limiting for API calls"""
        current_time = time.time()
        
        # Remove timestamps outside the window
        self._request_timestamps = [
            ts for ts in self._request_timestamps 
            if current_time - ts < self._rate_limit_window
        ]
        
        if len(self._request_timestamps) >= max_requests:
            sleep_time = self._rate_limit_window - (current_time - self._request_timestamps[0])
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached. Sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        self._request_timestamps.append(current_time)
    
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        jitter=backoff.full_jitter
    )
    def _store_data(self, data: Dict[str, Any], document_id: Optional[str] = None) -> str:
        """
        Store data in Firestore with retry logic
        
        Args:
            data: Data to store
            document_id: Optional custom document ID
            
        Returns:
            Document ID of stored data
        """
        try:
            # Add metadata
            data_with_metadata = {
                **data,
                '_ingested_at': SERVER_TIMESTAMP,
                '_source': self.source_name,
                '_processed_at': datetime.utcnow().isoformat()
            }
            
            if document_id:
                doc_ref = self.fire