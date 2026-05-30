#!/bin/bash
# 世界模型代码仓库Clone脚本
# 任务ID: B2B-20260531-000923
# 共18个仓库（跳过GAIA-1和Sora）

CODE_DIR="/home/lzy/project/方向研究/code"
mkdir -p "$CODE_DIR"
cd "$CODE_DIR" || exit 1

clone_repo() {
    local num=$1
    local name=$2
    local url=$3
    local dir
    if [ $num -lt 10 ]; then
        dir="0${num}_${name}"
    else
        dir="${num}_${name}"
    fi
    
    echo "[$num/18] Clone: $dir"
    if [ -d "$dir" ]; then
        echo "  -> 已存在，跳过"
        return 0
    fi
    
    for attempt in 1 2 3; do
        if git clone --depth 1 "$url" "$dir" 2>&1; then
            echo "  -> 成功"
            return 0
        else
            echo "  -> Clone失败 (attempt $attempt)，重试..."
            rm -rf "$dir"
        fi
        sleep 3
    done
    
    echo "  -> 最终失败"
    return 1
}

echo "=== 开始Clone世界模型代码仓库 ==="
echo ""

FAILED=0

clone_repo 1 "WorldModels" "https://github.com/worldmodels/worldmodels" || ((FAILED++))
clone_repo 2 "PlaNet" "https://github.com/google-research/planet" || ((FAILED++))
clone_repo 3 "Dreamer" "https://github.com/danijar/dreamer" || ((FAILED++))
clone_repo 4 "DreamerV2" "https://github.com/danijar/dreamerv2" || ((FAILED++))
clone_repo 5 "DreamerV3" "https://github.com/danijar/dreamerv3" || ((FAILED++))
clone_repo 6 "MuZero" "https://github.com/google-deepmind/mctx" || ((FAILED++))
clone_repo 7 "IRIS" "https://github.com/eloialonso/iris" || ((FAILED++))
clone_repo 8 "Genie" "https://github.com/genie-2024/genie" || ((FAILED++))
clone_repo 9 "UniSim" "https://github.com/universal-simulator/unisim" || ((FAILED++))
# #10 GAIA-1 跳过 (Wayve闭源)
clone_repo 11 "TDMPC" "https://github.com/nicklashansen/tdmpc" || ((FAILED++))
clone_repo 12 "TDMPC2" "https://github.com/nicklashansen/tdmpc2" || ((FAILED++))
clone_repo 13 "TransDreamer" "https://github.com/chenchancey/TransDreamer" || ((FAILED++))
clone_repo 14 "DayDreamer" "https://github.com/danijar/daydreamer" || ((FAILED++))
clone_repo 15 "SimPLe" "https://github.com/google-research/google-research" || ((FAILED++))
clone_repo 16 "DIAMOND" "https://github.com/eloialonso/diamond" || ((FAILED++))
clone_repo 17 "GameGenX" "https://github.com/GameGen-X/GameGen-X" || ((FAILED++))
clone_repo 18 "PhysDreamer" "https://github.com/PhysDreamer/PhysDreamer" || ((FAILED++))
clone_repo 19 "WALT" "https://github.com/snap-research/walt" || ((FAILED++))

echo ""
echo "=== 代码仓库Clone完成 ==="
echo "失败数: $FAILED"

# List results
echo ""
echo "已Clone仓库:"
for d in "$CODE_DIR"/*/; do
    if [ -d "$d/.git" ]; then
        size=$(du -sh "$d" 2>/dev/null | cut -f1)
        echo "  $(basename "$d"): $size"
    fi
done
echo ""
REPO_COUNT=$(ls -1d "$CODE_DIR"/*/ 2>/dev/null | wc -l)
echo "总仓库数: $REPO_COUNT"
