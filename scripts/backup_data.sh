#!/bin/bash
# 闲鱼 OpenClaw — SQLite 数据安全备份脚本
# 用法: bash scripts/backup_data.sh
# 可配合 crontab 或 launchd 定时执行
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_DIR="${BACKUP_DIR:-data/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_SUBDIR="$BACKUP_DIR/$TIMESTAMP"

mkdir -p "$BACKUP_SUBDIR"

echo "[backup] $(date '+%Y-%m-%d %H:%M:%S') Starting backup..."
echo "[backup] Destination: $BACKUP_SUBDIR"

# 备份所有 SQLite 数据库
BACKED_UP=0
for db_file in data/*.db data/**/*.db; do
    [ -f "$db_file" ] || continue

    db_name=$(basename "$db_file")
    backup_path="$BACKUP_SUBDIR/$db_name"

    # 使用 sqlite3 .backup 安全备份（不影响正在运行的进程）
    if command -v sqlite3 &>/dev/null; then
        sqlite3 "$db_file" ".backup '$backup_path'" 2>/dev/null
    else
        cp "$db_file" "$backup_path"
    fi

    if [ -f "$backup_path" ]; then
        size=$(du -h "$backup_path" | cut -f1)
        echo "[backup]   ✅ $db_name ($size)"
        BACKED_UP=$((BACKED_UP + 1))
    else
        echo "[backup]   ❌ $db_name (failed)"
    fi
done

# 备份配置文件
if [ -f ".env" ]; then
    cp ".env" "$BACKUP_SUBDIR/.env"
    echo "[backup]   ✅ .env"
    BACKED_UP=$((BACKED_UP + 1))
fi

if [ -f "config/config.yaml" ]; then
    cp "config/config.yaml" "$BACKUP_SUBDIR/config.yaml"
    echo "[backup]   ✅ config.yaml"
    BACKED_UP=$((BACKED_UP + 1))
fi

echo "[backup] Backed up $BACKED_UP files."

# 清理旧备份
echo "[backup] Cleaning backups older than ${KEEP_DAYS} days..."
CLEANED=0
for old_dir in "$BACKUP_DIR"/*/; do
    [ -d "$old_dir" ] || continue
    dir_name=$(basename "$old_dir")
    # 跳过非日期格式目录
    echo "$dir_name" | grep -qE '^[0-9]{8}_[0-9]{6}$' || continue

    # 检查文件夹修改时间
    if [ "$(find "$old_dir" -maxdepth 0 -mtime +${KEEP_DAYS} 2>/dev/null)" ]; then
        rm -rf "$old_dir"
        echo "[backup]   🗑️  Removed: $dir_name"
        CLEANED=$((CLEANED + 1))
    fi
done

echo "[backup] Cleaned $CLEANED old backups."
echo "[backup] Done."
