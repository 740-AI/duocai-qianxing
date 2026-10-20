#!/usr/bin/env bash
# ============================================================
# 多彩黔行 · PythonAnywhere 一键初始化脚本
# 用法：在 PythonAnywhere 的 Bash 控制台执行下面这一行：
#   curl -sL https://raw.githubusercontent.com/740-AI/duocai-qianxing/main/scripts/pa_setup.sh | bash
# 说明：脚本会克隆代码、创建虚拟环境、安装依赖
# ============================================================
set -e

PROJECT="$HOME/duocai-qianxing"
REPO="https://github.com/740-AI/duocai-qianxing.git"

echo "=== [1/4] 获取代码 ==="
if [ -d "$PROJECT/.git" ]; then
  cd "$PROJECT" && git pull --ff-only || true
else
  git clone --depth 1 "$REPO" "$PROJECT"
  cd "$PROJECT"
fi

echo "=== [2/4] 创建虚拟环境 ==="
if [ ! -d "$PROJECT/.venv" ]; then
  python3 -m venv "$PROJECT/.venv"
fi
source "$PROJECT/.venv/bin/activate"

echo "=== [3/4] 安装依赖 ==="
pip install --upgrade pip -q
pip install -q -r requirements.txt

echo "=== [4/4] 自检 ==="
cd "$PROJECT/app" && python -c "
import sys; sys.path.insert(0,'.')
from planner import plan
r = plan({'days':3,'people':2,'budget':3000,'mode':'selfdrive','tags':['自然']})
print('规划引擎自检通过：', r['summary']['spotCount'], '个景点，预估', r['summary']['estimatedTotal'], '元')
"

echo ""
echo "✅ 完成！项目位于 $PROJECT"
echo "下一步：到 Web 页面设置 Source code、Virtualenv、WSGI 文件"
