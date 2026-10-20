# 多彩黔行 —— 贵州文旅行程智能规划系统

> 2026 年第十四届全国大学生数字媒体科技作品及创意竞赛
> 自主选题类 · 移动与网络应用开发类赛项

## 快速启动

```bash
pip install flask   # 唯一依赖
python3 run.py      # 访问 http://127.0.0.1:5000
```

## 目录结构

```
duocai-qianxing/
├── run.py                    # 启动入口
├── app/
│   ├── server.py             # Flask 后端（API + 页面）
│   ├── planner.py            # 行程规划引擎（纯 Python，可独立运行）
│   ├── templates/index.html  # 前端页面（响应式）
│   ├── static/css/app.css    # 设计系统
│   ├── static/js/app.js      # 前端逻辑
│   └── static/manifest.json  # PWA 配置
├── data/guizhou.json         # 结构化文旅数据（25景点/10民宿/10美食/6主题）
├── data/app.db               # SQLite（分享/反馈/埋点，运行时自动创建）
├── docs/
│   ├── 系统说明与技术文档.md   # 提交用技术文档
│   ├── 截图/                  # 界面截图（6张）
│   └── 演示视频/功能演示.mp4   # 27秒操作演示
└── scripts/                  # 辅助脚本
```

## 独立测试规划引擎

```bash
cd app && python3 planner.py
```

## 核心算法

L1 候选评分 → L2 Morton空间切段 → L3 贪心插入+2-opt路线优化 → L4 时间轴排布（含用餐/住宿/预算约束）
