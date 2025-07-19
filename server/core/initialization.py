# services/initialization.py
import json
import os
from loguru import logger
from core.config import settings
from core.docker_manager import create_traefik_console_config
from core.faas_code import faas_templates
from core.minio_manager import minio_manager
from core.utils import create_mongodb_user, generate_short_id
from models.applications_model import (
    Application,
    CORSConfig,
    NotificationConfig,
    ApplicationStatus,
)
from models.functions_model import Function, FunctionStatus
from core.jwt_auth import create_refresh_token
from models.users_model import User
from models.function_template_model import FunctionTemplate, TemplateType, FunctionType
from models.tasks_model import Task, TaskAction
from routers.users import hash_password
from core.dependence_manager import dependence_manager


async def create_function_templates_for_app(app_id: str):
    """
    Creates a full set of function templates for a specific application.
    It checks for existence before creating to prevent duplicates for the given app.
    """
    try:
        for func_type, templates in faas_templates.items():
            for template_data in templates:
                name = template_data["name"]
                code = template_data["code"]
                description = template_data["description"]

                # Check if a template with the same name already exists for this app
                existing_template = await FunctionTemplate.find_one(
                    FunctionTemplate.name == name, FunctionTemplate.app_id == app_id
                )
                if existing_template:
                    logger.info(
                        f"Template '{name}' already exists for app '{app_id}', skipping creation."
                    )
                    continue

                # Create and insert the new template
                new_template = FunctionTemplate(
                    app_id=app_id,
                    name=name,
                    code=code,
                    type=TemplateType.SYSTEM,
                    shared=False,
                    description=description,
                    function_type=FunctionType(func_type),
                )
                await new_template.insert()
                logger.info(
                    f"Created system function template: '{name}' for app '{app_id}'"
                )
    except Exception as e:
        logger.error(
            f"Failed to create function templates for app '{app_id}': {e}",
            exc_info=True,
        )


class InitializationService:
    """
    Handles the initial setup of the application, including creating default
    users, applications, and functions if they don't exist.
    """

    @staticmethod
    async def initialize_console_bucket():
        """
        Initializes the 'console' bucket in MinIO for static website hosting
        and ensures its public read policy is correctly set on every startup.
        """
        bucket_name = "console"
        logger.info(f"Checking and initializing MinIO bucket: '{bucket_name}'...")
        try:
            # Ensure the bucket exists
            if not await minio_manager.bucket_exists(bucket_name):
                logger.info(f"Bucket '{bucket_name}' not found. Creating now...")
                await minio_manager.make_bucket(bucket_name)
                logger.info(f"Bucket '{bucket_name}' created successfully.")
            else:
                logger.info(f"Bucket '{bucket_name}' already exists.")

            # Define the required public read policy
            public_read_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                    },
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:ListBucket"],
                        "Resource": [f"arn:aws:s3:::{bucket_name}"],
                    },
                ],
            }
            policy_str = json.dumps(public_read_policy)

            # Get current policy
            current_policy_str = await minio_manager.get_bucket_policy(bucket_name)

            # Compare and set if different
            if current_policy_str:
                try:
                    current_policy = json.loads(current_policy_str)
                    if current_policy == public_read_policy:
                        logger.info(
                            f"Public read policy for bucket '{bucket_name}' is already correctly set."
                        )
                        return
                except json.JSONDecodeError:
                    logger.warning(
                        f"Could not parse existing policy for '{bucket_name}'. Overwriting."
                    )

            logger.info(
                f"Setting/updating public read policy for bucket '{bucket_name}'."
            )
            await minio_manager.set_bucket_policy(bucket_name, policy_str)
            logger.info(
                f"Successfully set public read policy for bucket '{bucket_name}'."
            )

        except Exception as e:
            logger.error(
                f"Error initializing console bucket '{bucket_name}': {e}", exc_info=True
            )

    @staticmethod
    async def initialize_default_user():
        """
        Initializes a default 'admin' user if one does not already exist.
        """
        default_username = settings.DEFAULT_ADMIN_USER
        default_password = settings.DEFAULT_ADMIN_PASSWORD

        if not default_username or not default_password:
            logger.error(
                "Default admin user or password is not set in the environment variables."
            )
            return

        hashed_password = hash_password(default_password)

        try:
            if not await User.find_one(User.username == default_username):
                token_data = {"sub": default_username}
                refresh_token = create_refresh_token(data=token_data)
                new_user = User(
                    username=default_username,
                    password=hashed_password,
                    nickname="Admin",
                    avatar_url="https://example.com/default_avatar.png",
                    roles=["admin"],
                    refresh_token=refresh_token,
                )
                await new_user.insert()
                logger.info(f"Created default user: '{default_username}'")
        except Exception as e:
            logger.error(f"Failed to create default user: {e}")

    @staticmethod
    async def initialize_demo_application():
        """
        Initializes a 'demo' application for testing and demonstration purposes.
        This includes creating a dedicated MongoDB user and a MinIO bucket.
        """
        try:
            if not await Application.find_one(Application.app_name == "demo"):
                demo_app = Application(
                    app_name="demo",
                    description="Default demo application for testing purposes.",
                    common_dependencies=[],
                    environment_variables=[],
                    users=["admin"],
                    db_password=generate_short_id(16),
                    cors=CORSConfig(
                        allow_origins=["*"],
                        allow_credentials=True,
                        allow_methods=["*"],
                        allow_headers=["*"],
                    ),
                    notification=NotificationConfig(),
                    status=ApplicationStatus.STARTING,
                )
                await demo_app.insert()
                logger.info(
                    f"Created initial demo application: 'demo' (ID: {demo_app.app_id})"
                )
                # Create a dedicated MongoDB user for the demo application.
                create_db_user_result = await create_mongodb_user(
                    username=demo_app.app_id,
                    password=demo_app.db_password,
                    target_db=demo_app.app_id,
                )
                if create_db_user_result:
                    logger.info(
                        f"Created MongoDB user for demo application: {demo_app.app_id}"
                    )
                else:
                    logger.error(
                        f"Failed to create MongoDB user for demo application: {demo_app.app_id}"
                    )

                # Create a dedicated MinIO bucket for the demo application.
                if minio_manager.client:
                    # Create main app bucket
                    app_bucket_name = demo_app.app_id.lower()
                    await minio_manager.make_bucket(app_bucket_name)
                    logger.info(f"Created MinIO bucket for demo app: {app_bucket_name}")

                    # Create and configure web hosting bucket
                    web_bucket_name = f"web-{demo_app.app_id.lower()}"
                    await minio_manager.make_bucket(web_bucket_name)
                    await minio_manager.set_bucket_to_public_read(web_bucket_name)
                    logger.info(
                        f"Created and configured web hosting bucket: {web_bucket_name}"
                    )

        except Exception as e:
            logger.error(f"Failed to create initial application: {e}")

    @staticmethod
    async def initialize_demo_functions():
        """
        Initializes a 'Hello' demo function within the 'demo' application.
        """
        demo_app = await Application.find_one({"app_name": "demo"})
        if not demo_app:
            logger.error("Application initialized failed")
            return
        demo_function = Function(
            function_name="Hello",
            app_id=demo_app.app_id,
            code=faas_templates["endpoint"][0][
                "code"
            ],  # Use the first endpoint template
            status=FunctionStatus.PUBLISHED,
            memory_limit=128,
            timeout=5,
            tags=["demo"],
            users=["admin"],  # Associate with the default user
            description="A simple demo function that returns a greeting.",
        )

        try:
            # Check if the function already exists.
            if not await Function.find_one(
                Function.function_name == "hello", Function.app_id == demo_app.app_id
            ):
                await demo_function.insert()
                logger.info(
                    f"Created initial demo function: /demo/hello (ID: {demo_function.function_id})"
                )
        except Exception as e:
            logger.error(f"Failed to create initial function: {e}")

    @classmethod
    async def initialize_functions_templates(cls):
        """
        Initializes function templates for the 'demo' application.
        """
        demo_app = await Application.find_one({"app_name": "demo"})
        if not demo_app:
            logger.error("Demo application not found, cannot initialize templates.")
            return
        await create_function_templates_for_app(demo_app.app_id)

    @staticmethod
    async def _is_database_empty() -> bool:
        """
        Checks if the functions, applications, and users collections are all empty.
        """
        functions_count = await Function.find_all().count()
        applications_count = await Application.find_all().count()
        users_count = await User.find_all().count()
        templates_count = await FunctionTemplate.find_all().count()
        return (
            functions_count == 0
            and applications_count == 0
            and users_count == 0
            and templates_count == 0
        )

    @classmethod
    async def initialize_existing_apps(cls):
        """
        Creates tasks to initialize containers for applications that should be running.
        """
        logger.info("Initializing existing applications by creating tasks...")
        try:
            # Find apps that are either running or were in the process of starting.
            apps_to_start = await Application.find(
                {
                    "status": {
                        "$in": [ApplicationStatus.RUNNING, ApplicationStatus.STARTING]
                    }
                }
            ).to_list()

            for app in apps_to_start:
                logger.info(
                    f"Creating start task for application: {app.app_name} (ID: {app.app_id}, Status: {app.status})"
                )
                # Set status to STARTING to reflect the current action
                app.status = ApplicationStatus.STARTING
                await app.save()

                # Create a task to start the application
                # task_id is now auto-generated by the model's default_factory
                task = Task(
                    action=TaskAction.START_APP,
                    payload={"app_id": app.app_id},
                )
                await task.insert()
                logger.info(f"Task '{task.task_id}' created for app '{app.app_id}'.")

        except Exception as e:
            logger.error(
                f"Failed to create initialization tasks for existing applications: {e}"
            )

    @classmethod
    async def check_and_initialize(cls):
        """
        Checks if initialization is needed and runs all initialization tasks.
        This is triggered if INIT_DEMO_FUNCTION is true and the database is empty or DEBUG is on.
        """
        # Generate Traefik config for the console on every startup.
        create_traefik_console_config()

        if await cls._is_database_empty():
            await cls.initialize_console_bucket()
            await cls.initialize_default_user()
            await cls.initialize_demo_application()
            # Dependencies will be installed by the app container on startup.
            await cls.initialize_demo_functions()
            await cls.initialize_functions_templates()
