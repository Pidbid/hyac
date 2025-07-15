import asyncio
from datetime import datetime
from loguru import logger

from models.tasks_model import Task, TaskStatus, TaskAction
from models.applications_model import Application, ApplicationStatus
from core.minio_manager import minio_manager

# 导入需要执行的函数
from core.docker_manager import (
    start_app_container,
    stop_app_container,
    docker_manager,
    delete_application_background,
)
from core.utils import create_mongodb_user, check_mongodb_user_exists


async def process_task(task: Task):
    """根据任务动作执行相应的操作"""
    logger.info(f"Processing task {task.task_id} with action {task.action}")

    # 更新任务状态为 running
    await task.update(
        {"$set": {Task.status: TaskStatus.RUNNING, "updated_at": datetime.now()}}
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
            # 1. 为应用创建数据库用户
            if not app.db_password:
                raise ValueError(f"DB password for app {app_id} is not set.")

            user_exists = await check_mongodb_user_exists(username=app.app_id)
            if not user_exists:
                logger.info(f"MongoDB user for app {app_id} not found, creating now...")
                user_created = await create_mongodb_user(
                    username=app.app_id, password=app.db_password, target_db=app.app_id
                )
                if not user_created:
                    raise Exception(f"Failed to create MongoDB user for app {app_id}.")
                logger.info(f"MongoDB user for app {app_id} created successfully.")
            else:
                logger.info(
                    f"MongoDB user for app {app_id} already exists, skipping creation."
                )

            # 2. 为应用创建 MinIO Buckets 并配置
            # 创建主应用 Bucket
            app_bucket_name = app.app_id.lower()
            if not await minio_manager.bucket_exists(app_bucket_name):
                logger.info(
                    f"MinIO bucket '{app_bucket_name}' not found, creating now..."
                )
                await minio_manager.make_bucket(app_bucket_name)
                logger.info(f"MinIO bucket '{app_bucket_name}' created successfully.")
            else:
                logger.info(
                    f"MinIO bucket '{app_bucket_name}' already exists, skipping creation."
                )

            # 创建并配置 Web 托管 Bucket
            web_bucket_name = f"web-{app.app_id.lower()}"
            if not await minio_manager.bucket_exists(web_bucket_name):
                logger.info(
                    f"MinIO web bucket '{web_bucket_name}' not found, creating now..."
                )
                await minio_manager.make_bucket(web_bucket_name)
                # 设置为公共读
                await minio_manager.set_bucket_to_public_read(web_bucket_name)
                logger.info(
                    f"MinIO web bucket '{web_bucket_name}' created and set to public read."
                )
            else:
                logger.info(
                    f"MinIO web bucket '{web_bucket_name}' already exists, skipping creation."
                )

            # 3. 启动应用容器
            result = await start_app_container(app)
            if not result:
                raise Exception("Failed to start application container.")

            # 4. 更新应用状态为 RUNNING
            app.status = ApplicationStatus.RUNNING
            await app.save()

        elif task.action == TaskAction.STOP_APP:
            await stop_app_container(app_id)
            app.status = ApplicationStatus.STOPPED
            await app.save()

        elif task.action == TaskAction.RESTART_APP:
            container_name = f"hyac-app-runtime-{app_id.lower()}"
            if not await docker_manager.restart_container(container_name):
                raise Exception("Failed to restart application container.")
            app.status = ApplicationStatus.RUNNING
            await app.save()

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
            {
                "$set": {
                    Task.status: TaskStatus.SUCCESS,
                    "result": {"message": "Task completed successfully."},
                    "updated_at": datetime.now(),
                }
            }
        )
        logger.info(f"Task {task.task_id} completed successfully.")

    except Exception as e:
        error_message = f"Task {task.task_id} failed: {str(e)}"
        logger.error(error_message, exc_info=True)
        # 更新任务状态为 failed 并记录错误
        await task.update(
            {
                "$set": {
                    Task.status: TaskStatus.FAILED,
                    "result": {"error": error_message},
                    "updated_at": datetime.now(),
                }
            }
        )
        # 如果是启动失败，将应用状态设置为 ERROR
        if task.action == TaskAction.START_APP and app:
            app.status = ApplicationStatus.ERROR
            await app.save()


async def reconcile_running_apps():
    """
    Ensures that all applications marked as RUNNING in the database are
    actually running as Docker containers on startup.
    """
    logger.info("Reconciling running applications state...")
    try:
        # 1. Get all apps that should be running from the database
        expected_running_apps = await Application.find(
            Application.status == ApplicationStatus.RUNNING
        ).to_list()
        if not expected_running_apps:
            logger.info(
                "No applications are expected to be running. Reconciliation complete."
            )
            return

        # 2. Get all currently running hyac app containers from Docker
        running_containers = docker_manager.list_containers()
        running_app_container_names = {
            c["name"]
            for c in running_containers
            if c["name"].startswith("hyac-app-runtime-")
        }

        # 3. Compare and create startup tasks for missing apps
        apps_to_restart_count = 0
        for app in expected_running_apps:
            container_name = f"hyac-app-runtime-{app.app_id.lower()}"
            if container_name not in running_app_container_names:
                apps_to_restart_count += 1
                logger.warning(
                    f"App '{app.app_name}' ({app.app_id}) is marked as RUNNING but its container "
                    f"'{container_name}' is not found. Creating a new startup task."
                )
                # Create a new task to start this app
                await Task(
                    action=TaskAction.START_APP,
                    payload={"app_id": app.app_id},
                    status=TaskStatus.PENDING,
                ).insert()

        if apps_to_restart_count > 0:
            logger.info(
                f"Created {apps_to_restart_count} startup tasks for missing apps."
            )
        else:
            logger.info(
                "All expected running applications are active. No action needed."
            )

    except Exception as e:
        logger.error(
            f"Error during application state reconciliation: {e}", exc_info=True
        )


async def process_pending_tasks():
    """
    Processes pending or failed startup tasks on startup.
    This ensures that applications that failed to start previously get a retry.
    """
    logger.info(
        "Checking for pending or failed startup tasks from previous sessions..."
    )
    tasks_to_process = await Task.find(
        {
            "$or": [
                {"status": TaskStatus.PENDING},
                {
                    "status": TaskStatus.FAILED,
                    "action": TaskAction.START_APP,
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
    # First, reconcile the state of running applications.
    await reconcile_running_apps()

    # Then, process any tasks that were pending from a previous run.
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
        logger.error(f"Task watcher failed: {e}", exc_info=True)
        # Consider a retry mechanism or alerting here
