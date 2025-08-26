@echo off
echo Starting YouTube Audio Mixer...
echo.
echo This will open the app in your default web browser.
echo If it doesn't open automatically, go to: http://localhost:8501
echo.
echo Press Ctrl+C to stop the app when you're done.
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9+ and try again
    pause
    exit /b 1
)

REM Check if streamlit is installed
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Streamlit is not installed
    echo Installing required packages...
    pip install streamlit yt-dlp
    if errorlevel 1 (
        echo ERROR: Failed to install packages
        pause
        exit /b 1
    )
)

REM Check if yt-dlp is available
yt-dlp --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: yt-dlp is not installed or not in PATH
    echo The app may not work properly for YouTube downloads
    echo You can install it with: pip install yt-dlp
    echo.
)

REM Check if ffmpeg is available
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo WARNING: ffmpeg is not installed or not in PATH
    echo The app may not work properly for audio processing
    echo Please install ffmpeg and add it to your PATH
    echo.
)

echo Starting the app...
echo.

REM Run the Streamlit app
streamlit run streamlit_app.py

REM If we get here, the app was closed
echo.
echo App closed. Press any key to exit.
pause >nul
