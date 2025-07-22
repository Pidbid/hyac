# core/faas_minio.py
import io
import mimetypes
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import BinaryIO, Iterator, Optional, TextIO, Union, cast

from loguru import logger
from minio.error import S3Error

from core.minio_manager import minio_manager

# Context variable to store the app_id for bucket resolution.
app_id_context: ContextVar[str] = ContextVar("app_id_context")


def _parse_mode(mode: str) -> dict[str, bool]:
    """Parses the file mode string."""
    mode_map = {
        "read": "r" in mode,
        "write": "w" in mode,
        "append": "a" in mode,
        "exclusive": "x" in mode,
        "update": "+" in mode,
        "binary": "b" in mode,
    }
    if (
        sum(
            [
                mode_map["read"],
                mode_map["write"],
                mode_map["append"],
                mode_map["exclusive"],
            ]
        )
        > 1
    ):
        raise ValueError("Modes 'r', 'w', 'a', and 'x' cannot be combined.")
    if mode_map["exclusive"] and mode_map["update"]:
        raise ValueError("Mode 'x+' is invalid.")
    return mode_map


@contextmanager
def _streaming_read(
    bucket_name: str,
    object_name: str,
    file_path: str,
    mode_binary: bool,
    encoding: str,
    retries: int = 3,
    delay: float = 0.1,
) -> Iterator[Union[TextIO, BinaryIO]]:
    """Handles streaming read logic with retries for eventual consistency."""
    response = None
    last_exception = None
    for attempt in range(retries):
        try:
            response = minio_manager.client.get_object(bucket_name, object_name)
            # If successful, break the loop and proceed
            break
        except S3Error as e:
            last_exception = e
            if e.code == "NoSuchKey" and attempt < retries - 1:
                logger.warning(
                    f"Attempt {attempt + 1}/{retries}: File '{file_path}' not found, retrying in {delay}s..."
                )
                time.sleep(delay)
                continue
            # For other S3 errors or last retry failure, re-raise
            raise IOError(f"Could not access MinIO object '{file_path}'.") from e
        except Exception as e:
            # For non-S3 errors, fail immediately
            logger.error(f"MinIO streaming read failed for '{file_path}': {e}")
            raise IOError(f"Could not access MinIO object '{file_path}'.") from e

    if not response:
        raise FileNotFoundError(
            f"File '{file_path}' not found after {retries} retries."
        ) from last_exception

    try:
        stream: Union[TextIO, BinaryIO]
        if mode_binary:
            stream = cast(BinaryIO, response)
        else:
            stream = io.TextIOWrapper(cast(BinaryIO, response), encoding=encoding)
        yield stream
    finally:
        if response:
            response.close()
            response.release_conn()


@contextmanager
def _buffered_read_write(
    bucket_name: str,
    object_name: str,
    file_path: str,
    modes: dict[str, bool],
    encoding: str,
    content_type: Optional[str],
) -> Iterator[Union[TextIO, BinaryIO]]:
    """Handles buffered read and write logic."""
    initial_data = b""
    main_mode = "r"
    if modes["write"]:
        main_mode = "w"
    elif modes["append"]:
        main_mode = "a"
    elif modes["exclusive"]:
        main_mode = "x"

    # --- Preparation Phase ---
    try:
        if main_mode == "x":
            try:
                minio_manager.client.stat_object(bucket_name, object_name)
                raise FileExistsError(
                    f"File '{file_path}' already exists, cannot use 'x' mode."
                )
            except S3Error as e:
                if e.code != "NoSuchKey":
                    raise
        elif (main_mode in ["r", "a"]) or (modes["update"] and main_mode != "w"):
            try:
                response = minio_manager.client.get_object(bucket_name, object_name)
                with response:
                    initial_data = response.read()
            except S3Error as e:
                if e.code == "NoSuchKey":
                    if main_mode == "r":
                        raise FileNotFoundError(f"File '{file_path}' not found.") from e
                else:
                    raise
    except Exception as e:
        logger.error(f"MinIO operation preparation failed for '{file_path}': {e}")
        raise IOError(f"Could not access MinIO object '{file_path}'.") from e

    # --- Buffer Creation and Management ---
    buffer: Union[io.StringIO, io.BytesIO]
    if modes["binary"]:
        buffer = io.BytesIO(initial_data)
    else:
        buffer = io.StringIO(initial_data.decode(encoding))

    if main_mode == "a":
        buffer.seek(0, io.SEEK_END)
    else:
        buffer.seek(0)

    # --- Yield Phase ---
    try:
        yield buffer
    finally:
        # --- Cleanup and Upload Phase ---
        if main_mode in ["w", "a", "x"] or modes["update"]:
            try:
                buffer.seek(0)
                # Efficiently get data length and prepare for upload
                if isinstance(buffer, io.StringIO):
                    final_content = buffer.read()
                    upload_data = final_content.encode(encoding)
                    upload_stream = io.BytesIO(upload_data)
                    data_len = len(upload_data)
                else:  # io.BytesIO
                    data_len = buffer.getbuffer().nbytes
                    upload_stream = buffer  # Reuse the buffer directly

                # Determine content type
                final_content_type = content_type
                if not final_content_type:
                    guessed_type, _ = mimetypes.guess_type(object_name)
                    final_content_type = guessed_type or "application/octet-stream"

                minio_manager.client.put_object(
                    bucket_name,
                    object_name,
                    upload_stream,
                    data_len,
                    content_type=final_content_type,
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
            buffer.close()


@contextmanager
def minio_open(
    file_path: str,
    mode: str = "r",
    encoding: str = "utf-8",
    streaming: bool = False,
    content_type: Optional[str] = None,
) -> Iterator[Union[TextIO, BinaryIO]]:
    """
    A context manager to read from and write to MinIO objects as if they were local files.
    Supports modes like r, w, a, x, +, and b.

    Args:
        file_path: The full path to the MinIO object.
        mode: The file mode, similar to the built-in open() function.
        encoding: The encoding to use in text mode.
        streaming: If True and in read-only mode, streams the file. Otherwise, buffers it.
        content_type: The MIME type of the file. If None, it's inferred from the file extension.

    Yields:
        A file-like object for interaction.
    """
    if not minio_manager.client:
        raise IOError("MinIO client is not initialized.")

    bucket_name = app_id_context.get(None)
    if not bucket_name:
        raise IOError(
            "Cannot determine bucket name because app_id is not set in the context."
        )

    bucket_name = bucket_name.lower()
    object_name = file_path.lstrip("/")

    modes = _parse_mode(mode)

    is_simple_read = modes["read"] and not (
        modes["write"] or modes["append"] or modes["exclusive"] or modes["update"]
    )

    if is_simple_read and streaming:
        with _streaming_read(
            bucket_name, object_name, file_path, modes["binary"], encoding
        ) as stream:
            yield stream
    else:
        with _buffered_read_write(
            bucket_name, object_name, file_path, modes, encoding, content_type
        ) as buffer:
            yield buffer
