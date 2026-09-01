import os
import time
import logging
from dotenv import load_dotenv

# Provide .env variables before importing other modules
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from .sync import run_sync

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SyncScheduler")

def start_scheduler():
    """Starts a blocking scheduler for the background sync operations"""
    # Create APS Scheduler
    scheduler = BlockingScheduler()
    
    # Get cron schedule from environment variable or use default "0 2 * * *" (Every day at 2 AM)
    cron_schedule = os.getenv('SYNC_CRON', '0 2 * * *')
    parts = cron_schedule.split()
    
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        
        # Exception handling wrap
        def safe_run_sync():
            try:
                run_sync(mode="incremental")
            except Exception as e:
                logger.error(f"Scheduled sync encountered an error, but scheduler will continue. Error: {str(e)}", exc_info=True)

        scheduler.add_job(
            func=safe_run_sync,
            trigger="cron",
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            id='sync_job_cron',
            name="Incremental Knowledge Base Sync"
        )
        
        logger.info(f"Scheduler successfully attached with cron schedule: {cron_schedule}")
    else:
        logger.error(f"Invalid cron format provided: {cron_schedule}")
        return
    
    try:
        logger.info("Initializing background scheduler... (Press Ctrl+C to terminate)")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler gracefully stopped by user or system.")
    except Exception as e:
        logger.error(f"Scheduler encountered a critical failure: {str(e)}")
        
if __name__ == "__main__":
    start_scheduler()