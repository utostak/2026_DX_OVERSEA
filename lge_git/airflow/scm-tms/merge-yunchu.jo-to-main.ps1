#requires -Version 5.1
<#
.SYNOPSIS
    yunchu.jo 브랜치를 main 으로 머지하고 origin 에 푸시합니다. (운영 배포)

.DESCRIPTION
    LIW 운영 배포용 Git 스크립트입니다.

    동작 순서:
      1) 작업 트리가 깨끗한지 확인 (커밋 안 된 변경 있으면 중단)
      2) origin 최신 상태로 fetch
      3) main 에 반영될 yunchu.jo 커밋 목록 표시
      4) (확인) main 체크아웃 → origin/main ff-only pull
      5) yunchu.jo 를 --no-ff 로 머지 (릴리스 머지 커밋 생성)
      6) origin/main 으로 push  →  GitLab CI(start-job-main)가 운영 서버 자동 배포
      7) 원래 브랜치(yunchu.jo)로 복귀

    ※ main 으로 push 되는 순간 운영 배포가 트리거됩니다.

.PARAMETER NoConfirm
    push 전 확인 프롬프트를 건너뜁니다. (CI/자동화용)

.PARAMETER KeepBranch
    완료 후 yunchu.jo 로 돌아가지 않고 main 에 머무릅니다.

.PARAMETER DryRun
    실제 머지/푸시 없이, main 에 반영될 yunchu.jo 커밋만 미리 봅니다.

.EXAMPLE
    .\merge-yunchu.jo-to-main.ps1
        # 확인 프롬프트를 거쳐 yunchu.jo -> main 머지 & 배포

.EXAMPLE
    .\merge-yunchu.jo-to-main.ps1 -DryRun
        # 무엇이 배포될지 미리 확인만

.EXAMPLE
    .\merge-yunchu.jo-to-main.ps1 -NoConfirm
        # 확인 없이 바로 진행
#>
param(
    [switch]$NoConfirm,
    [switch]$KeepBranch,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 은 ErrorActionPreference=Stop 상태에서 git 의 stderr
# 출력(예: "Switched to branch ...")을 NativeCommandError 로 던집니다.
# git 이 모든 출력을 stdout 으로 보내도록 하여 이 문제를 근본적으로 차단합니다.
$env:GIT_REDIRECT_STDERR = '2>&1'

$SOURCE = 'yunchu.jo'
$TARGET = 'main'

# ── 출력 헬퍼 ────────────────────────────────────────────────
function Info ($m) { Write-Host "  $m" -ForegroundColor Gray }
function Step ($m) { Write-Host "▶ $m" -ForegroundColor Cyan }
function Ok   ($m) { Write-Host "✔ $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "⚠ $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "✗ $m" -ForegroundColor Red; exit 1 }

# ── git 실행 헬퍼 (실패 시 중단) ─────────────────────────────
function Git-Run {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) { Die "git $($GitArgs -join ' ')  (exit $LASTEXITCODE)" }
}

# ── 0. 저장소 루트로 이동 & git 저장소 확인 ─────────────────
$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0) { Die "git 저장소가 아닙니다. 프로젝트 폴더에서 실행하세요." }
Set-Location $repoRoot

$startBranch = (& git rev-parse --abbrev-ref HEAD).Trim()
Step "현재 브랜치: $startBranch  |  저장소: $repoRoot"

# ── 1. 작업 트리 클린 확인 (DryRun 은 읽기 전용이므로 건너뜀) ──
if (-not $DryRun) {
    if ((& git status --porcelain)) {
        Die "커밋되지 않은 변경이 있습니다. 먼저 commit / stash 후 다시 실행하세요."
    }
    Ok "작업 트리 클린"
}

# ── 2. 최신 상태 fetch ──────────────────────────────────────
Step "origin fetch 중..."
Git-Run fetch origin --prune
Ok "fetch 완료"

# 원격에 두 브랜치가 모두 존재하는지 확인
& git show-ref --verify --quiet "refs/remotes/origin/$SOURCE"
if ($LASTEXITCODE -ne 0) { Die "origin/$SOURCE 가 존재하지 않습니다." }
& git show-ref --verify --quiet "refs/remotes/origin/$TARGET"
if ($LASTEXITCODE -ne 0) { Die "origin/$TARGET 가 존재하지 않습니다." }

# 로컬 yunchu.jo 에 push 되지 않은 커밋이 있는지 확인
# (이 스크립트는 'origin/yunchu.jo' 를 운영으로 승격합니다)
$localSourceExists = $false
& git show-ref --verify --quiet "refs/heads/$SOURCE"
if ($LASTEXITCODE -eq 0) { $localSourceExists = $true }

if ($localSourceExists) {
    $ahead = (& git rev-list --count "origin/$SOURCE..$SOURCE").Trim()
    if ([int]$ahead -gt 0) {
        Warn "로컬 $SOURCE 에 origin/$SOURCE 로 push 되지 않은 커밋이 $ahead 개 있습니다."
        Warn "이 스크립트는 origin/$SOURCE 를 기준으로 배포하므로, 해당 커밋은 운영에 반영되지 않습니다."
        Info "필요하면 먼저  git push origin $SOURCE  실행 후 다시 시도하세요."
    }
}

# ── 3. main 에 반영될 yunchu.jo 커밋 목록 ────────────────────
$pending = & git log --oneline "origin/$TARGET..origin/$SOURCE"
if (-not $pending) {
    Ok "origin/$TARGET 는 이미 origin/$SOURCE 와 동기화되어 있습니다. 머지할 내용이 없습니다."
    exit 0
}

Write-Host ""
Write-Host "── $SOURCE → $TARGET 에 반영될 커밋 ──────────────────────" -ForegroundColor Magenta
$pending | ForEach-Object { Write-Host "  $_" -ForegroundColor White }
$count = ($pending | Measure-Object).Count
Write-Host "────────────────────────────────────────────────────────" -ForegroundColor Magenta
Info "총 $count 개 커밋"
Write-Host ""

if ($DryRun) {
    Warn "DryRun 모드 — 실제 머지/푸시는 수행하지 않았습니다."
    exit 0
}

# ── 4. 배포 확인 ────────────────────────────────────────────
Warn "main 으로 push 하면 GitLab CI 가 '운영 서버'에 자동 배포합니다."
if (-not $NoConfirm) {
    $ans = Read-Host "계속 진행할까요? (yes 입력 시 진행)"
    if ($ans -ne 'yes') { Die "사용자가 취소했습니다." }
}

# 실패/중단 시 원래 브랜치로 되돌리기 위한 정리 함수
function Restore-Branch {
    if (-not $KeepBranch) {
        $cur = (& git rev-parse --abbrev-ref HEAD).Trim()
        if ($cur -ne $startBranch) {
            # --quiet 로 'Switched to branch' 메시지를 끄고, 리다이렉트는 사용하지 않습니다.
            & git checkout --quiet $startBranch
            if ($LASTEXITCODE -eq 0) { Info "원래 브랜치($startBranch)로 복귀" }
        }
    }
}

try {
    # ── 5. main 체크아웃 & ff-only pull ─────────────────────
    Step "$TARGET 체크아웃"
    Git-Run checkout $TARGET

    Step "origin/$TARGET ff-only pull"
    & git pull --ff-only origin $TARGET
    if ($LASTEXITCODE -ne 0) {
        Die "$TARGET 가 origin/$TARGET 와 분기되어 ff-only pull 실패. 수동 확인이 필요합니다."
    }

    # ── 6. yunchu.jo 머지 (--no-ff: 릴리스 머지 커밋 생성) ───
    # origin/yunchu.jo 를 기준으로 머지 → 위 미리보기 목록과 정확히 일치
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $msg   = "Merge $SOURCE into $TARGET (release $stamp)"
    Step "origin/$SOURCE 머지 (--no-ff)"
    & git merge --no-ff "origin/$SOURCE" -m $msg
    if ($LASTEXITCODE -ne 0) {
        Warn "머지 충돌 발생 — 머지를 abort 합니다."
        & git merge --abort
        Die "충돌로 머지가 중단되었습니다. $SOURCE 의 변경을 main 기준으로 정리 후 다시 시도하세요."
    }
    Ok "머지 완료: $msg"

    # ── 7. push (→ 운영 배포 트리거) ────────────────────────
    Step "origin/$TARGET push"
    Git-Run push origin $TARGET
    Ok "push 완료 — GitLab CI 운영 배포가 시작됩니다."
}
finally {
    Restore-Branch
}

Write-Host ""
Ok "$SOURCE → main 배포 스크립트 완료 ($count 커밋 반영)"
