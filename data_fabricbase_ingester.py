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