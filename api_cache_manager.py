"""
api_cache_manager.py
─────────────────────────────────────────────────────────────────────────────
Manages Gemini API rate limiting via:
  1. Request caching (hash-based deduplication)
  2. Request queuing (throttled execution)
  3. Exponential backoff with jitter
  4. Graceful degradation with quality warnings
─────────────────────────────────────────────────────────────────────────────
"""

import hashlib
import json
import logging
import time
import threading
from pathlib import Path
from typing import Optional, Tuple
from collections import deque
from datetime import datetime, timedelta

log = logging.getLogger("api_cache_manager")

# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST CACHE (hash-based deduplication)
# ═══════════════════════════════════════════════════════════════════════════════

class RequestCache:
    """File-based cache for API responses keyed by image hash."""
    
    def __init__(self, cache_dir: str = "./api_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl_hours = 24  # Cache expires after 24 hours
        log.info(f"Cache initialized at {self.cache_dir}")
    
    def _get_image_hash(self, image_path: str) -> str:
        """Compute SHA256 hash of image file."""
        sha256 = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _get_cache_path(self, image_hash: str) -> Path:
        """Get cache file path for hash."""
        return self.cache_dir / f"{image_hash}.json"
    
    def get(self, image_path: str) -> Optional[dict]:
        """
        Retrieve cached response for image.
        Returns None if not cached or expired.
        """
        try:
            image_hash = self._get_image_hash(image_path)
            cache_path = self._get_cache_path(image_hash)
            
            if not cache_path.exists():
                return None
            
            # Check if cache is expired
            mtime = cache_path.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            
            if age_hours > self.ttl_hours:
                log.info(f"Cache expired for {image_hash[:8]}… (age: {age_hours:.1f}h)")
                cache_path.unlink()
                return None
            
            with open(cache_path, "r") as f:
                data = json.load(f)
            
            log.info(f"Cache HIT for {image_hash[:8]}… (age: {age_hours:.1f}h)")
            return data
        
        except Exception as e:
            log.warning(f"Cache read error: {e}")
            return None
    
    def set(self, image_path: str, response: dict) -> None:
        """Store response in cache."""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_path = self._get_cache_path(image_hash)
            
            with open(cache_path, "w") as f:
                json.dump(response, f, indent=2)
            
            log.info(f"Cache SET for {image_hash[:8]}…")
        except Exception as e:
            log.warning(f"Cache write error: {e}")
    
    def clear(self) -> None:
        """Clear all cached responses."""
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
        log.info("Cache cleared")


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST QUEUE (throttled + ordered execution)
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimitedQueue:
    """
    Queue that executes requests with rate limiting.
    - Max 10 requests per minute (leaves room for spikes)
    - FIFO ordering (fairness)
    - Thread-safe
    """
    
    def __init__(self, max_requests_per_minute: int = 10):
        self.max_requests = max_requests_per_minute
        self.window_seconds = 60
        self.request_times = deque()  # timestamps of recent requests
        self.lock = threading.Lock()
        log.info(f"RateLimitedQueue initialized: {max_requests_per_minute} req/min")
    
    def wait_if_needed(self) -> float:
        """
        Block until we're under the rate limit.
        Returns: wait time in seconds.
        """
        with self.lock:
            now = time.time()
            
            # Remove old timestamps outside the window
            while self.request_times and self.request_times[0] < now - self.window_seconds:
                self.request_times.popleft()
            
            # If we're at the limit, sleep
            if len(self.request_times) >= self.max_requests:
                oldest_request = self.request_times[0]
                wait_time = (oldest_request + self.window_seconds) - now
                
                if wait_time > 0:
                    log.warning(f"Rate limit approaching — waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                    now = time.time()
            
            # Record this request
            self.request_times.append(now)
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# RETRY LOGIC (exponential backoff with jitter)
# ═══════════════════════════════════════════════════════════════════════════════

class RetryConfig:
    """Configuration for retries with exponential backoff."""
    
    def __init__(self, max_attempts: int = 5, base_delay: float = 2.0, max_delay: float = 60.0, jitter: bool = True):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
    
    def get_wait_time(self, attempt: int) -> float:
        """
        Calculate wait time for attempt N.
        Exponential: 2s, 3s, 5s, 9s, 17s, capped at 60s
        With jitter: add ±20% randomness to avoid thundering herd
        """
        import random
        
        wait_time = min(self.base_delay * (2 ** attempt), self.max_delay)
        
        if self.jitter:
            jitter_amount = wait_time * 0.2 * (2 * random.random() - 1)  # ±20%
            wait_time += jitter_amount
        
        return max(0.1, wait_time)  # Never wait less than 0.1s


# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY TRACKER (detect degradation)
# ═══════════════════════════════════════════════════════════════════════════════

class QualityTracker:
    """Track extraction quality and detect when falling back to regex."""
    
    def __init__(self):
        self.stats = {
            "vision_api_success": 0,
            "vision_api_rate_limit": 0,
            "vision_api_failure": 0,
            "regex_fallback": 0,
        }
        self.lock = threading.Lock()
    
    def record_success(self, source: str) -> None:
        """Record successful extraction."""
        with self.lock:
            if source == "vision":
                self.stats["vision_api_success"] += 1
            log.debug(f"Quality: {source} success — total successes: {self.stats['vision_api_success']}")
    
    def record_rate_limit(self) -> None:
        """Record 429 rate limit error."""
        with self.lock:
            self.stats["vision_api_rate_limit"] += 1
            rate = self.stats["vision_api_rate_limit"]
            if rate % 5 == 0:
                log.warning(f"⚠️  RATE LIMIT #({rate}) — API quota may be exhausted")
    
    def record_fallback(self) -> None:
        """Record fallback to regex extraction."""
        with self.lock:
            self.stats["regex_fallback"] += 1
            total_fallbacks = self.stats["regex_fallback"]
            log.warning(f"⚠️  REGEX FALLBACK #{total_fallbacks} — extraction quality degraded")
    
    def get_summary(self) -> dict:
        """Get current quality statistics."""
        with self.lock:
            total = sum(self.stats.values())
            if total == 0:
                return {"status": "no_data"}
            
            success_rate = 100 * self.stats["vision_api_success"] / total if total > 0 else 0
            
            return {
                "total_requests": total,
                "vision_api_success": self.stats["vision_api_success"],
                "vision_api_failures": self.stats["vision_api_rate_limit"] + self.stats["vision_api_failure"],
                "regex_fallbacks": self.stats["regex_fallback"],
                "success_rate_pct": f"{success_rate:.1f}%",
            }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCES
# ═══════════════════════════════════════════════════════════════════════════════

# Global singletons
_cache = None
_queue = None
_retry_config = None
_quality_tracker = None


def init_cache_manager(cache_dir: str = "./api_cache", max_requests_per_minute: int = 10):
    """Initialize global cache manager instances."""
    global _cache, _queue, _retry_config, _quality_tracker
    
    _cache = RequestCache(cache_dir)
    _queue = RateLimitedQueue(max_requests_per_minute)
    _retry_config = RetryConfig()
    _quality_tracker = QualityTracker()
    
    log.info("✓ Cache manager initialized")


def get_cache() -> RequestCache:
    global _cache
    if _cache is None:
        init_cache_manager()
    return _cache


def get_queue() -> RateLimitedQueue:
    global _queue
    if _queue is None:
        init_cache_manager()
    return _queue


def get_retry_config() -> RetryConfig:
    global _retry_config
    if _retry_config is None:
        init_cache_manager()
    return _retry_config


def get_quality_tracker() -> QualityTracker:
    global _quality_tracker
    if _quality_tracker is None:
        init_cache_manager()
    return _quality_tracker
