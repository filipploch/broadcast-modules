@echo off
echo ========================================
echo Building OBS WebSocket Plugin
echo ========================================
echo.

echo Downloading dependencies...
go mod download
if errorlevel 1 (
    echo ERROR: Failed to download dependencies
    exit /b 1
)

echo.
echo Building for Windows (amd64)...
set GOOS=windows
set GOARCH=amd64
go build -o obs-ws-plugin.exe main.go
if errorlevel 1 (
    echo ERROR: Build failed
    exit /b 1
)

echo.
echo ========================================
echo Build successful!
echo ========================================
echo Output: obs-ws-plugin.exe
echo.

dir obs-ws-plugin.exe
