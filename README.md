# trilium-diary

把开发过程中的关键节点（踩坑、工作里程碑、技术决策、学习笔记）以 markdown 形式记入
[Trilium Notes](https://github.com/zadam/trilium) 的日历 / Journal 面板。

## 安装

```bash
# 项目级（仅当前项目生效）
git clone https://github.com/<user>/trilium-diary.git .claude/skills/trilium-diary

# 全局（所有项目生效）
git clone https://github.com/<user>/trilium-diary.git ~/.claude/skills/trilium-diary
```

## 配置

```bash
cp etc/config.example.json etc/config.json
```

编辑 `etc/config.json`，填入你的 Trilium 服务器地址、ETAPI token 和日历根笔记 ID。

## 使用

```bash
# 检查连通性
./scripts/trilium.py check

# 写入一条日记
./scripts/trilium.py add --type work --title "联调通过" <<< '## 背景\n...\n## 结果\n...'

# 列出日记
./scripts/trilium.py list --date 2026-05-29
```

`--type` 选项：`trap`（踩坑）、`work`（工作）、`decision`（决策）、`learn`（学习）。

## 依赖

Python 3.12+，通过 [uv](https://docs.astral.sh/uv/) 自动管理依赖（`markdown`、`requests`）。
