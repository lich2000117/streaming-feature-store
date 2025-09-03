#!/usr/bin/env python3
"""
Training Job Scheduler

Runs the ML training pipeline at regular intervals to keep models up-to-date
with the latest data from the feature store.

Usage:
    python scheduler.py --interval 600  # Run every 10 minutes
"""

import os
import time
import logging
import subprocess
import click
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TrainingScheduler:
    """Schedules and manages periodic training jobs."""
    
    def __init__(self, interval: int, timeout: int):
        self.interval = interval
        self.timeout = timeout
        self.last_success = None
        
    def run_forever(self):
        """Run training jobs at regular intervals."""
        logger.info(f"Starting training scheduler with {self.interval}s interval")
        
        while True:
            try:
                self._run_training_job()
                self._wait_for_next_run()
            except KeyboardInterrupt:
                logger.info("Scheduler stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in scheduler: {e}")
                time.sleep(60)  # Wait a bit before retrying
                
    def _run_training_job(self):
        """Execute a single training job."""
        start_time = datetime.now()
        logger.info(f"Starting scheduled training job at {start_time}")
        
        try:
            # Run training script with timeout
            result = subprocess.run(
                ['python', 'train.py'],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0:
                self.last_success = datetime.now()
                duration = (self.last_success - start_time).total_seconds()
                logger.info(f"Training completed successfully in {duration:.1f}s")
            else:
                logger.error(f"Training failed with exit code {result.returncode}")
                logger.error(f"Error output: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error(f"Training job timed out after {self.timeout}s")
        except Exception as e:
            logger.error(f"Error running training job: {e}")
            
    def _wait_for_next_run(self):
        """Wait for next scheduled run."""
        if self.last_success:
            logger.info(f"Last successful training: {self.last_success}")
        
        next_run = datetime.now().timestamp() + self.interval
        next_run_time = datetime.fromtimestamp(next_run)
        logger.info(f"Next training scheduled for: {next_run_time}")
        time.sleep(self.interval)

@click.command()
@click.option('--interval', default=600, help='Training interval in seconds')
@click.option('--timeout', default=300, help='Training job timeout in seconds')
def main(interval: int, timeout: int):
    """Run training scheduler."""
    scheduler = TrainingScheduler(interval, timeout)
    scheduler.run_forever()

if __name__ == '__main__':
    main()
