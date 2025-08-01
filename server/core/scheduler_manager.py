import asyncio
from typing import Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from models.scheduled_tasks_model import ScheduledTask, TriggerType
from core.scheduled_runner import run_function
from core.runtime_status_manager import sync_runtime_status


# Mapping of system task IDs to their corresponding callable functions
SYSTEM_TASK_RUNNERS = {
    "system_sync_runtime_status": sync_runtime_status,
}


class SchedulerManager:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def _get_trigger(self, trigger_type: TriggerType, trigger_config: Dict[str, Any]):
        """Creates a trigger instance from config."""
        if trigger_type == TriggerType.CRON:
            return CronTrigger(**trigger_config)
        elif trigger_type == TriggerType.INTERVAL:
            return IntervalTrigger(**trigger_config)
        else:
            raise ValueError(f"Unsupported trigger type: {trigger_type}")

    async def add_job(self, task: ScheduledTask):
        """Adds a job to the scheduler based on a task document."""
        if not task.enabled:
            logger.info(f"Task '{task.name}' ({task.task_id}) is disabled, skipping.")
            # Ensure disabled tasks are removed from the scheduler
            if self.scheduler.get_job(task.task_id):
                self.scheduler.remove_job(task.task_id)
                logger.info(
                    f"Removed disabled job '{task.name}' ({task.task_id}) from scheduler."
                )
            return

        try:
            trigger = self._get_trigger(task.trigger, task.trigger_config)

            # Check if the task is a system task
            if task.is_system_task:
                runner = SYSTEM_TASK_RUNNERS.get(task.task_id)
                if not runner:
                    logger.error(
                        f"No runner found for system task '{task.name}' ({task.task_id})."
                    )
                    return
                # Schedule the system task runner directly
                self.scheduler.add_job(
                    runner,
                    trigger=trigger,
                    id=task.task_id,
                    name=task.name,
                    replace_existing=True,
                )
            else:
                # For non-system tasks, ensure app_id and function_id are present
                if not task.app_id or not task.function_id:
                    logger.error(
                        f"Task '{task.name}' ({task.task_id}) is missing app_id or function_id."
                    )
                    return
                # Schedule a regular user-defined function
                self.scheduler.add_job(
                    run_function,
                    trigger=trigger,
                    args=[task.app_id, task.function_id, task.params, task.body],
                    id=task.task_id,
                    name=task.name,
                    replace_existing=True,
                )
            logger.info(
                f"Successfully added/updated job '{task.name}' ({task.task_id})."
            )
        except Exception as e:
            logger.error(
                f"Failed to add job for task '{task.name}' ({task.task_id}): {e}"
            )

    async def remove_job(self, task_id: str):
        """Removes a job from the scheduler."""
        try:
            if self.scheduler.get_job(task_id):
                self.scheduler.remove_job(task_id)
                logger.info(f"Successfully removed job '{task_id}'.")
        except Exception as e:
            logger.error(f"Failed to remove job '{task_id}': {e}")

    async def load_jobs_from_db(self):
        """Loads all enabled tasks from the database and adds them to the scheduler."""
        logger.info("Loading scheduled jobs from database...")
        tasks = await ScheduledTask.find(ScheduledTask.enabled == True).to_list()
        count = 0
        for task in tasks:
            await self.add_job(task)
            count += 1
        logger.info(f"Loaded {count} scheduled jobs.")

    async def start(self):
        """
        Starts the scheduler in a safe manner, ensuring jobs are loaded
        before scheduling begins.
        """
        if not self.scheduler.running:
            # Start the scheduler in a paused state to prevent race conditions
            self.scheduler.start(paused=True)
            logger.info("Scheduler started in paused state.")

            # Load all jobs from the database
            await self.load_jobs_from_db()

            # Resume the scheduler to start job execution
            self.scheduler.resume()
            logger.info("Scheduler resumed and now running.")

    def shutdown(self):
        """Shuts down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shut down.")


# Create a singleton instance
scheduler_manager = SchedulerManager()
