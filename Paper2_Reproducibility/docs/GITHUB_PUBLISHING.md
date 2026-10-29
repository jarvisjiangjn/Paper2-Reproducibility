# GitHub 发布操作（Windows）

本文用于把本项目作为一个独立 GitHub 仓库发布。发布前请先确认代码及实验结果的公开权限。

## 1. 发布前检查

1. 阅读 `docs/PREPUBLICATION_CHECKLIST.md`。
2. 确认共同作者同意公开代码、实验输出及论文关联信息。
3. 本仓库暂未附项目代码许可证。与共同作者确认后再添加合适的 `LICENSE`；不要直接把数据集的许可证当作本项目代码许可证。
4. 检查 `results/` 和 `baseline_results/` 中的实验输出是否可以公开。上游数据的许可证仍然适用。
5. 确认 `config.json`、`.env`、API Key、私有数据、未公开论文内容均未加入 Git。

## 2. 安装 Git 并配置身份

安装 Git for Windows：<https://git-scm.com/download/win>。安装后打开 PowerShell，执行：

```powershell
git --version
git config --global user.name "你的 GitHub 显示名称"
git config --global user.email "你的 GitHub 邮箱"
```

邮箱建议使用 GitHub 提供的 noreply 邮箱，以减少公开个人邮箱的风险。

## 3. 在 GitHub 创建空仓库

1. 登录 <https://github.com/new>。
2. 仓库名可使用 `Paper2-Reproducibility`。
3. 根据论文发布计划选择 Public 或 Private。
4. 创建时先不要勾选初始化 README、`.gitignore` 或 License，避免与本地项目发生首次提交冲突。
5. 复制 GitHub 页面提供的仓库 HTTPS 地址。

## 4. 从本地上传

先解压本项目 ZIP。下面假设解压目录为 `D:\Research\Paper2_Reproducibility`，请替换为你自己的实际路径：

```powershell
cd D:\Research\Paper2_Reproducibility
git init
git status
git add .
git status
```

第二次 `git status` 会列出准备上传的文件。确认没有密钥、私有数据或不应公开的内容后再提交：

```powershell
git commit -m "Initial reproducible release for Paper 2"
git branch -M main
git remote add origin https://github.com/你的用户名/Paper2-Reproducibility.git
git push -u origin main
```

GitHub 可能会要求在浏览器中完成身份验证。不要把 GitHub 密码或访问令牌写进代码、配置文件或命令历史。

## 5. 后续更新

每次修改后，先检查差异：

```powershell
git status
git diff
```

确认后提交并推送：

```powershell
git add README.md README_zh-CN.md engine tests docs
git add run_unified.py verify_sqlite.py preflight_spider.py scripts requirements.txt config.example.json run_windows.bat frozen_scenarios.jsonl .gitignore
git commit -m "Describe the change"
git push
```

如果还要发布更新后的实验结果，请在检查数据许可和隐私后，明确添加相应结果文件，不要无差别地上传整个工作目录。

## 6. 公开仓库的建议

- 初次发布可先设为 Private，完成合作者审阅、许可证确认和结果核验后再切换 Public。
- 为论文正式版本创建 Git tag，例如 `v1.0.0`，并在论文或补充材料中引用对应的 GitHub Release/commit。
- API 实验可能产生费用；README 已说明必须显式传入 `--enable-api` 才会调用模型服务。
- 当前测试可在项目根目录执行：

```powershell
python -m unittest discover -s tests -v
```

或在已安装 pytest 的环境中执行 `python -m pytest -q`。
