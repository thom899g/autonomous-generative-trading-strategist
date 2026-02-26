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