import asyncio
from datetime import datetime
from beanie.odm.operators.update.general import Set
from loguru import logger

from models.tasks_model import Task, TaskStatus, TaskAction
from models.applications_model import Application

# 导入需要执行的函数
from core.docker_manager import (
    start_app_container,
    stop_app_container,
    docker_manager,
    delete_application_background,
)


async def process_task(task: Task):
    """根据任务动作执行相应的操作"""
    logger.info(f"Processing task {task.task_id} with action {task.action}")

    # 更新任务状态为 running
    await task.update(
        Set({Task.status: TaskStatus.RUNNING, "updated_at": datetime.now()})
    )

    try:
        app_id = task.payload.get("app_id")
        if not app_id:
            raise ValueError("app_id is missing in task payload")

        app = await Application.find_one(Application.app_id == app_id)
        # For delete action, app might be None if it's already marked for deletion or gone
        if not app and task.action != TaskAction.DELETE_APP:
            raise ValueError(f"Application with app_id {app_id} not found")

        # --- 核心任务分发逻辑 ---
        if task.action == TaskAction.START_APP:
            result = await start_app_container(app)
            if not result:
                raise Exception("Failed to start application container.")

        elif task.action == TaskAction.STOP_APP:
            await stop_app_container(app_id)

        elif task.action == TaskAction.RESTART_APP:
            container_name = f"hyac-app-runtime-{app_id.lower()}"
            if not docker_manager.restart_container(container_name):
                raise Exception("Failed to restart application container.")

        elif task.action == TaskAction.DELETE_APP:
            # The app object might have been deleted by the time the task runs.
            # The delete_application_background function handles all cleanup.
            # We need to pass the app object to it.
            if app:
                await delete_application_background(app)
            else:
                logger.warning(
                    f"Application {app_id} already deleted, skipping delete task."
                )

        # 更新任务状态为 success
        await task.update(
            Set(
                {
                    Task.status: TaskStatus.SUCCESS,
                    "result": {"message": "Task completed successfully."},
                    "updated_at": datetime.now(),
                }
            )
        )
        logger.info(f"Task {task.task_id} completed successfully.")

    except Exception as e:
        error_message = f"Task {task.task_id} failed: {str(e)}"
        logger.error(error_message)
        # 更新任务状态为 failed 并记录错误
        await task.update(
            Set(
                {
                    Task.status: TaskStatus.FAILED,
                    "result": {"error": error_message},
                    "updated_at": datetime.now(),
                }
            )
        )


async def process_pending_tasks():
    """
    Processes pending tasks on startup.
    This includes all tasks in the PENDING state, and any START_APP tasks that have FAILED,
    to ensure that applications that should be running are started.
    """
    logger.info(
        "Checking for pending or failed startup tasks from previous sessions..."
    )
    tasks_to_process = await Task.find(
        {
            "$or": [
                {"status": TaskStatus.PENDING},
                {
                    "action": TaskAction.START_APP,
                    "status": TaskStatus.FAILED,
                },
            ]
        }
    ).to_list()

    if not tasks_to_process:
        logger.info("No pending or failed startup tasks found to process.")
        return

    logger.info(
        f"Found {len(tasks_to_process)} tasks to process. Processing them now..."
    )
    for task in tasks_to_process:
        asyncio.create_task(process_task(task))


async def watch_for_tasks():
    """Watches for new tasks and processes pending tasks on startup."""
    # First, process any tasks that were pending from a previous run.
    await process_pending_tasks()

    logger.info("Task worker started, watching for new tasks...")
    collection = Task.get_motor_collection()

    # 只监听新插入的、状态为 PENDING 的任务
    pipeline = [
        {
            "$match": {
                "operationType": "insert",
                "fullDocument.status": TaskStatus.PENDING,
            }
        }
    ]

    try:
        async with collection.watch(pipeline, full_document="updateLookup") as stream:
            async for change in stream:
                doc = change["fullDocument"]
                task = Task.parse_obj(doc)
                # 使用 asyncio.create_task 来并发处理任务，避免阻塞监听循环
                asyncio.create_task(process_task(task))
    except Exception as e:
        logger.error(f"Task watcher failed: {e}")
        # Consider a retry mechanism or alerting here
