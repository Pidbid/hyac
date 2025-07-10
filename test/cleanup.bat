@echo off
echo Stopping containers and removing volumes...
cd ..
docker-compose down -v

echo.
echo Removing Docker images...
docker rmi hyac_server:latest
docker rmi hyac_app:latest
docker rmi hyac_lsp:latest
docker rmi hyac_uploader:latest

echo.
echo Removing temporary Nginx configs...
cd nginx\conf.d
for %%f in (*.conf) do (
    if /i not "%%f"=="oss.conf" (
        if /i not "%%f"=="server.conf" (
            if /i not "%%f"=="lsp.conf" (
                if /i not "%%f"=="console.conf" (
                    echo Deleting %%f
                    del "%%f"
                )
            )
        )
    )
)
cd ..\..

echo.
echo Cleanup complete.
