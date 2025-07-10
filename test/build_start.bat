@echo off
echo Starting building images and running...
echo ---------------------------------------
echo ----------------- Building hyac server ----------------- 
cd ../server
docker build -t hyac_server:latest .

echo.
echo ---------------------------------------
echo ----------------- Building hyac app ----------------- 
cd ../app
docker build -t hyac_app:latest .

echo ---------------------------------------
echo ----------------- Building hyac lsp ----------------- 
cd ../lsp
docker build -t hyac_lsp:latest .


echo ---------------------------------------
echo ----------------- Building hyac web uploader ----------------- 
cd ../uploader
docker build -t hyac_uploader:latest .
echo.

echo ---------------------------------------
echo ----------------- Start ----------------- 
cd ..
docker-compose up -d

echo.
echo Cleanup complete.
