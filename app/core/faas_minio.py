# core/faas_minio.py
import io
from contextlib import contextmanager
from contextvars import ContextVar
from typing import BinaryIO, Iterator, TextIO, Union, cast

from loguru import logger
from minio.error import S3Error

from core.minio_manager import minio_manager

# Context variable to store the app_id for bucket resolution.
app_id_context: ContextVar[str] = ContextVar("app_id_context")


@contextmanager
def minio_open(
    file_path: str,
    mode: str = "r",
    encoding: str = "utf-8",
    streaming: bool = False,
) -> Iterator[Union[TextIO, BinaryIO]]:
    """
    A context manager to read from and write to MinIO objects as if they were local files.
    Supports modes like r, w, a, x, +, and b.

    Args:
        file_path: The full path to the MinIO object, formatted as 'bucket_name/object_name'.
        mode: The file mode, similar to the built-in open() function.
        encoding: The encoding to use in text mode.
        streaming: If True and in read-only mode, streams the file. Otherwise, buffers it.

    Yields:
        A file-like object for interaction.
    """
    if not minio_manager.client:
        raise IOError("MinIO client is not initialized.")

    # Get the app_id from the context variable to use as the bucket name.
    bucket_name = app_id_context.get(None)
    if not bucket_name:
        raise IOError(
            "Cannot determine bucket name because app_id is not set in the context."
        )

    bucket_name = bucket_name.lower()
    object_name = file_path[1:] if file_path.startswith("/") else file_path

    # Parse the mode string.
    mode_read = "r" in mode
    mode_write = "w" in mode
    mode_append = "a" in mode
    mode_exclusive = "x" in mode
    mode_update = "+" in mode
    mode_binary = "b" in mode

    # --- Streaming Read Logic (if requested) ---
    is_simple_read = mode_read and not (
        mode_write or mode_append or mode_exclusive or mode_update
    )

    if is_simple_read and streaming:
        response = None
        try:
            response = minio_manager.client.get_object(bucket_name, object_name)
            stream: Union[TextIO, BinaryIO]
            if mode_binary:
                stream = cast(BinaryIO, response)
            else:
                # The response object is file-like and can be wrapped by TextIOWrapper.
                # We cast it to satisfy the type checker.
                stream = io.TextIOWrapper(cast(BinaryIO, response), encoding=encoding)

            try:
                yield stream
            finally:
                stream.close()

        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(f"File '{file_path}' not found.") from e
            logger.error(f"MinIO streaming read failed for '{file_path}': {e}")
            raise IOError(f"Could not access MinIO object '{file_path}'.") from e
        except Exception as e:
            logger.error(f"MinIO streaming read failed for '{file_path}': {e}")
            raise IOError(f"Could not access MinIO object '{file_path}'.") from e
        finally:
            if response:
                response.release_conn()
        return  # We are done, exit the context manager.

    # --- Buffered Read/Write Logic (Default behavior) ---

    # Validate mode combinations.
    if sum([mode_read, mode_write, mode_append, mode_exclusive]) > 1:
        raise ValueError("Modes 'r', 'w', 'a', and 'x' cannot be combined.")

    # Determine the primary operation.
    main_mode = "r"
    if mode_write:
        main_mode = "w"
    elif mode_append:
        main_mode = "a"
    elif mode_exclusive:
        main_mode = "x"

    if main_mode == "x" and mode_update:
        raise ValueError("Mode 'x+' is invalid.")

    # Initialize buffer and state.
    initial_data = b""
    is_new_file = False

    # --- Preparation Phase ---
    try:
        # For exclusive mode, check if the file already exists.
        if main_mode == "x":
            try:
                minio_manager.client.stat_object(bucket_name, object_name)
                raise FileExistsError(
                    f"File '{file_path}' already exists, cannot use 'x' mode."
                )
            except S3Error as e:
                if e.code == "NoSuchKey":
                    is_new_file = True
                else:
                    raise

        # For read, append, or update modes (except 'w+'), fetch existing content first.
        if (main_mode in ["r", "a"]) or (mode_update and main_mode != "w"):
            try:
                response = minio_manager.client.get_object(bucket_name, object_name)
                with response:
                    initial_data = response.read()
            except S3Error as e:
                if e.code == "NoSuchKey":
                    if main_mode == "r":
                        raise FileNotFoundError(f"File '{file_path}' not found.") from e
                    # For 'a' or 'w+'/'a+', file not existing is acceptable.
                    is_new_file = True
                else:
                    raise

    except Exception as e:
        logger.error(f"MinIO operation preparation failed: {e}")
        raise IOError(f"Could not access MinIO object '{file_path}'.") from e

    # --- Buffer Creation and Management ---
    buffer: Union[TextIO, BinaryIO]
    if mode_binary:
        buffer = io.BytesIO(initial_data)
    else:
        buffer = io.StringIO(initial_data.decode(encoding))

    # Adjust buffer pointer based on the mode.
    if main_mode == "a":
        buffer.seek(0, io.SEEK_END)  # Move to the end
    else:
        buffer.seek(0)  # Move to the beginning

    # --- Yield Phase ---
    try:
        yield buffer
    finally:
        # --- Cleanup and Upload Phase ---
        # Only upload if the mode involves writing.
        if main_mode in ["w", "a", "x"] or mode_update:
            try:
                buffer.seek(0)
                final_content = buffer.read()

                if isinstance(final_content, str):
                    upload_data = final_content.encode(encoding)
                elif isinstance(final_content, bytes):
                    upload_data = final_content
                else:
                    upload_data = str(final_content).encode(encoding)

                upload_stream = io.BytesIO(upload_data)
                data_len = len(upload_data)

                minio_manager.client.put_object(
                    bucket_name, object_name, upload_stream, data_len
                )
                logger.info(
                    f"File '{object_name}' successfully written to bucket '{bucket_name}'."
                )

            except Exception as e:
                logger.error(f"Failed to upload to MinIO: {e}")
                raise IOError(
                    f"Could not write changes to MinIO file '{file_path}'."
                ) from e
            finally:
                buffer.close()
        else:
            # For read-only mode, just close the buffer.
            buffer.close()
