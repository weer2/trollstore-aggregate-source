@echo off
chcp 65001 >nul
REM ============================================================
REM  一键部署到 GitHub（Windows）
REM  前提：1) 已在 GitHub 网页创建一个空公开仓库（不要勾选初始化 README）
REM        2) 本机已安装 Git 并登录 GitHub（Git Credential Manager）
REM  用法：双击运行，按提示输入仓库地址
REM ============================================================
setlocal

echo.
echo ============================================================
echo   巨魔聚合动态源 - 一键部署到 GitHub
echo ============================================================
echo.

set /p REPO_URL="请输入你的 GitHub 仓库地址 (例如 https://github.com/weer2/trollstore-aggregate-source.git): "

if "%REPO_URL%"=="" (
    echo [错误] 未输入仓库地址。
    pause
    exit /b 1
)

echo.
echo [1/4] 初始化本地仓库...
if not exist ".git" (
    git init
    git config user.name "weer2"
    git config user.email "weer2@users.noreply.github.com"
)

echo [2/4] 添加全部文件...
git add -A

echo [3/4] 提交...
git commit -m "feat: 11网盘聚合动态源系统 - 免密码直采 + 每日自动更新" 2>nul
if errorlevel 1 (
    echo   (无变更或已提交，继续)
)

echo [4/4] 推送到 GitHub...
git branch -M main
git remote remove origin 2>nul
git remote add origin "%REPO_URL%"
git push -u origin main --force

if errorlevel 1 (
    echo.
    echo [失败] 推送失败。请确认：
    echo   1. 仓库地址正确且已创建
    echo   2. Git 已登录 GitHub（运行 git config --global credential.helper manager）
    echo   3. 若有代理问题，尝试：git config --global http.sslVerify false
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  部署成功！
echo  订阅地址：
echo  %REPO_URL:.git=%
echo.
echo  请将上面地址末尾加：/raw/main/output/source.json
echo  完整订阅地址示例：
echo  https://raw.githubusercontent.com/weer2/trollstore-aggregate-source/main/output/source.json
echo ============================================================
echo.
echo  IMPORTANT: 到仓库 Settings - Actions - General,
echo  将 Workflow permissions 设为 "Read and write" 以启用每日定时更新。
echo.
pause
