@echo off
REM ============================================================
REM Publish this folder as a new public repo on github.com/Milad-Shabani
REM Requires: git, and GitHub CLI (gh) installed + logged in (gh auth login)
REM
REM NOTE ON RENAMING YOUR OLD "vitrina-crm-ops-intelligence" REPO:
REM   Running this script with a new REPO_NAME creates a BRAND NEW repo -
REM   it does NOT rename or touch your existing "vitrina-crm-ops-intelligence"
REM   repo on GitHub. If you'd rather rename the old one in place (keeping
REM   its stars/issues/history) instead of creating a second repo, run this
REM   ONE command first, then skip straight to a normal `git push`:
REM       gh repo rename marketco-marketplace-intelligence --repo Milad-Shabani/vitrina-crm-ops-intelligence
REM   That renames the GitHub repo itself; your local folder's remote URL
REM   will keep working automatically (GitHub redirects the old name).
REM ============================================================

set REPO_NAME=marketco-marketplace-intelligence
set REPO_DESC=MarketCo: synthetic marketplace operations + Dynamics 365-style CRM dataset (580K+ orders, 260 sellers, 36K customers) with a LightGBM order-forecasting model, a customer-churn classifier with RFM segmentation, and Excel + interactive HTML dashboard reporting.

REM --- adjust this to wherever you unzipped/cloned the project locally
cd /d "C:\Users\MILAD\Desktop\marketco-marketplace-intelligence"

REM --- set your git identity (safe to run every time)
git config --global user.name "Milad Shabani"
git config --global user.email "MILAD.SHABANI6515@GMAIL.COM"

REM --- init only if not already a repo
if not exist ".git" (
    git init
    git branch -M main
)

REM --- remove any leftover remote from a previous attempt
git remote remove origin 2>nul

git add .
git commit -m "Initial commit: MarketCo - marketplace operations & CRM intelligence platform"
git branch -M main

gh repo create %REPO_NAME% --public --source=. --remote=origin --push --description "%REPO_DESC%"
if errorlevel 1 (
    echo.
    echo [ERROR] gh repo create failed - see the message above.
    echo Common causes: a repo named %REPO_NAME% already exists on your account,
    echo or you are not logged in ^(run: gh auth login^).
    pause
    exit /b 1
)

gh repo edit Milad-Shabani/%REPO_NAME% --add-topic data-science --add-topic crm --add-topic dynamics-365 --add-topic churn-prediction --add-topic demand-forecasting --add-topic lightgbm --add-topic ecommerce --add-topic python --add-topic dashboard

echo.
echo Done. Repo should now be live at:
echo https://github.com/Milad-Shabani/%REPO_NAME%
pause
