#!/bin/bash
# 世界模型论文PDF下载脚本
# 任务ID: B2B-20260531-000923
# 共19篇论文

PAPER_DIR="/home/lzy/project/方向研究/papers"
mkdir -p "$PAPER_DIR"
cd "$PAPER_DIR" || exit 1

download_pdf() {
    local num=$1
    local name=$2
    local url=$3
    local file="0${num}_${name}.pdf"
    # Fix filename for double-digit numbers
    if [ $num -ge 10 ]; then
        file="${num}_${name}.pdf"
    fi
    
    echo "[$num/19] 下载: $file"
    if [ -f "$file" ]; then
        echo "  -> 已存在，跳过"
        return 0
    fi
    
    for attempt in 1 2 3; do
        if curl -L -o "$file" --connect-timeout 30 --max-time 120 -s -f "$url"; then
            local size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
            if [ "$size" -gt 10000 ]; then
                echo "  -> 成功 ($size bytes)"
                return 0
            else
                echo "  -> 文件太小，可能下载失败，重试..."
                rm -f "$file"
            fi
        else
            echo "  -> 下载失败 (attempt $attempt)，重试..."
            rm -f "$file"
        fi
        sleep 2
    done
    
    echo "  -> 最终失败"
    return 1
}

echo "=== 开始下载世界模型论文PDF ==="
echo ""

FAILED=0

download_pdf 1 "Ha_2018_WorldModels" "https://arxiv.org/pdf/1803.10122" || ((FAILED++))
download_pdf 2 "Hafner_2019_PlaNet" "https://arxiv.org/pdf/1811.04551" || ((FAILED++))
download_pdf 3 "Hafner_2020_Dreamer" "https://arxiv.org/pdf/1912.01603" || ((FAILED++))
download_pdf 4 "Hafner_2021_DreamerV2" "https://arxiv.org/pdf/2010.02193" || ((FAILED++))
download_pdf 5 "Hafner_2023_DreamerV3" "https://arxiv.org/pdf/2301.04104" || ((FAILED++))
download_pdf 6 "Schrittwieser_2020_MuZero" "https://arxiv.org/pdf/1911.08265" || ((FAILED++))
download_pdf 7 "Micheli_2023_IRIS" "https://arxiv.org/pdf/2209.00588" || ((FAILED++))
download_pdf 8 "Bruce_2024_Genie" "https://arxiv.org/pdf/2402.15391" || ((FAILED++))
download_pdf 9 "Yang_2024_UniSim" "https://arxiv.org/pdf/2310.06114" || ((FAILED++))
download_pdf 10 "Hu_2023_GAIA1" "https://arxiv.org/pdf/2309.17080" || ((FAILED++))
download_pdf 11 "Hansen_2022_TDMPC" "https://arxiv.org/pdf/2203.04955" || ((FAILED++))
download_pdf 12 "Hansen_2024_TDMPC2" "https://arxiv.org/pdf/2310.16828" || ((FAILED++))
download_pdf 13 "Chen_2022_TransDreamer" "https://arxiv.org/pdf/2202.09481" || ((FAILED++))
download_pdf 14 "Wu_2022_DayDreamer" "https://arxiv.org/pdf/2206.14176" || ((FAILED++))
download_pdf 15 "Kaiser_2020_SimPLe" "https://arxiv.org/pdf/1903.00374" || ((FAILED++))
download_pdf 16 "Alonso_2024_DIAMOND" "https://arxiv.org/pdf/2405.12399" || ((FAILED++))
download_pdf 17 "Che_2024_GameGenX" "https://arxiv.org/pdf/2411.00769" || ((FAILED++))
download_pdf 18 "Zhang_2024_PhysDreamer" "https://arxiv.org/pdf/2404.13026" || ((FAILED++))
download_pdf 19 "Gupta_2024_WALT" "https://arxiv.org/pdf/2312.06662" || ((FAILED++))

echo ""
echo "=== PDF下载完成 ==="
echo "失败数: $FAILED"

# List results
echo ""
echo "已下载文件:"
ls -lh "$PAPER_DIR"/*.pdf 2>/dev/null | awk '{print $5, $9}'
echo ""
PDF_COUNT=$(ls -1 "$PAPER_DIR"/*.pdf 2>/dev/null | wc -l)
echo "总PDF文件数: $PDF_COUNT"
