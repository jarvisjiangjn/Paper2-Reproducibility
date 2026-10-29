# Paper 2：面向 Text-to-SQL 数据智能体的权限感知 SQL 修订

本仓库用于公开 Paper 2 的实验原型及 D1 结果。系统根据列级访问策略检查初始 SQL；对于越权查询，可以运行有界修订策略；最终候选还要通过确定性的授权检查和依赖审计。

> **结果范围：** D1 使用基准中的查询—权限记录，并将参考 SQL 作为初始提案。这些数据不是从已部署的数据智能体中采集的真实生成结果。通过授权检查或成功执行 SQL，都不能单独证明语义等价或回答充分。

## 目录内容

- `run_unified.py`：D1/D3 统一实验入口。
- `engine/`：API 请求、SQL 修订、授权检查和依赖审计代码。
- `verify_sqlite.py`：后置、只读的 SQLite 执行审计。
- `preflight_spider.py`：检查 D1 所需的 SQLite 数据库是否齐全。
- `scripts/download_access_control_dataset.py`：下载并校验 D1 使用的 Spider-ACL 输入数据。
- `scripts/install_spider_database.py`：从已下载的 Spider 压缩包中安装数据库文件。
- `frozen_scenarios.jsonl`：D3 冻结的合成恢复场景。
- `baseline_results/D1/`：`deny_only` 和 `rule` 的离线基线结果。
- `results/D1/`：三种 LLM 修订方法的结果和 SQLite 执行审计。
- `config.example.json`：不含密钥的模型配置示例。

下载的数据和本地密钥不会放进仓库。

## 环境要求

- Windows 10/11 支持通过 `run_windows.bat` 操作；其他系统也可直接执行 Python 命令。
- Python 3.10 或更新版本。
- 核心实验只依赖 Python 标准库，不需要额外 `pip install`。
- LLM 修订实验需要兼容 OpenAI Chat Completions API 的服务和有效 API Key。

## 1. 准备数据

### 1.1 下载 Spider-ACL 数据（D1 必需）

执行：

```powershell
python scripts/download_access_control_dataset.py
```

脚本会从官方 [LLM-Access-Control-Datasets 仓库](https://github.com/klisura-code/LLM-Access-Control-Datasets)下载压缩包，提取 `spider-access-control.jsonl`，检查字段和 19,624 条记录，然后将文件保存到 `data/access_control_dataset.jsonl`。

脚本会校验本仓库已发布 D1 结果所用输入文件的 SHA-256。如果上游数据已变化，脚本会停止，避免把不同版本的数据与已发布结果混用。如果你确实要使用更新后的数据，可运行：

```powershell
python scripts/download_access_control_dataset.py --force --allow-updated-source
```

使用更新版本后，请将实验输出保存到新的目录，并重新核对论文中的结果。

数据来源与引用：

- Klisura 等人，*Role-Conditioned Refusals: Evaluating Access Control Reasoning in Large Language Models*，Findings of EACL 2026：[论文](https://aclanthology.org/2026.findings-eacl.316/)。
- [官方数据仓库](https://github.com/klisura-code/LLM-Access-Control-Datasets)。

### 1.2 下载 Spider SQLite 数据库（执行审计必需）

D1 的授权判断和修订实验不需要本地 SQLite 数据库；后置执行审计需要数据库文件。

1. 从 [Spider 官方项目页面](https://yale-lily.github.io/spider)下载 Spider 1.0 数据压缩包。官方页面标明数据采用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可。
2. 将 ZIP 保存在项目目录之外也可以。
3. 运行下面的命令，只安装 SQLite 数据库文件和 `tables.json`：

```powershell
python scripts/install_spider_database.py --archive "C:\path\to\spider.zip"
```

脚本会将数据库放到 `data/spider/database/<db_id>/<db_id>.sqlite`。如果本地已经安装了数据库，只有在确实需要替换时才添加 `--overwrite`。

### 1.3 检查数据

```powershell
python preflight_spider.py
```

检查结果会保存到 `results/spider_preflight.json`，其中会明确列出缺失或无法读取的数据库。

## 2. 配置模型 API

先复制配置示例：

```powershell
Copy-Item config.example.json config.json
```

如有需要，再编辑 `config.json` 中的服务地址、模型名称、超时和重试次数。随后在当前 PowerShell 会话中设置 API Key：

```powershell
$env:PAPER2_API_KEY = "YOUR_API_KEY"
```

不要将 `config.json`、`.env` 或真实 API Key 上传到 GitHub。`.gitignore` 已排除本地配置和下载的数据。

## 3. 运行实验

### 3.1 D1 离线基线

```powershell
python run_unified.py --dataset D1 --methods deny_only rule --out reproduced_results/baseline
```

### 3.2 D1 前 20 条 API 试跑

```powershell
python run_unified.py --dataset D1 --methods naive_retry sql_aware_retry diagnostic_revision --max-cases 20 --enable-api --out reproduced_results/pilot
```

确认配置和 API 费用后，再运行全量实验。

### 3.3 D1 LLM 全量实验

```powershell
python run_unified.py --dataset D1 --methods naive_retry sql_aware_retry diagnostic_revision --enable-api --out reproduced_results/D1
```

程序会输出 JSONL 逐条结果、manifest 和 `summary.json`。Manifest 记录输入哈希、方法、模型标识和协议设置。如果现有输出的 manifest 与本次配置不一致，程序会拒绝混合续跑。换模型或换数据时，请使用新的输出目录。

### 3.4 D3 冻结案例实验

```powershell
python run_unified.py --dataset D3 --methods deny_only rule naive_retry sql_aware_retry diagnostic_revision --enable-api --out reproduced_results/D3
```

该命令会运行 `frozen_scenarios.jsonl` 当前包含的全部记录。**该文件包含 88 条场景记录，其中交通领域 44 条、能源领域 44 条。** 在将实验结果作为论文中的 D3 结果报告前，应核对场景数量、实际使用的场景集合与论文描述是否一致。

### 3.5 SQLite 执行审计

D1 实验完成后运行：

```powershell
python verify_sqlite.py --results reproduced_results/D1 --out reproduced_results/D1/execution_audit.csv
```

只有通过授权检查和依赖审计的候选才会进入只读 SQLite 执行。默认 CSV 不包含原始查询结果样本值，也不重复保存基准问题和原始 SQL。需要查看原始上下文时，可通过 `scenario_id` 与下载的 D1 输入关联；本地人工检查时也可以添加 `--include-context`。只有在确有需要时才添加 `--include-samples`，并在发布前检查数据许可和必要性。

`executed` 只表示 SQL 在当前 SQLite 环境下成功执行，不代表 SQL 与原始请求语义等价。

## 4. 当前公开结果

仓库保留了 D1 离线基线、三种 LLM 修订方法的逐条结果、manifest、summary 和 SQLite 执行审计。公开版执行审计 CSV 不包含原始数据库结果样本，也不重复保存基准问题和原始 SQL；这些上下文可通过 `scenario_id` 与下载的数据关联。执行状态统计和查询输出哈希没有因此改变。部分结果中的候选 SQL 与初始获授权记录的基准 SQL 相同；再次分发或使用这些记录时，应遵守上游数据许可并引用原始数据集。

当前仓库包含冻结的 D3 场景文件，但尚未包含 D3 实验输出 JSONL、manifest、summary，以及独立的人工语义审计表。在核对场景数量、论文描述和审计版本之前，不应将 D3 结果表述为论文结果的完整复现。详细状态见 [`docs/REPRODUCIBILITY_NOTES.md`](docs/REPRODUCIBILITY_NOTES.md)。

## 5. 解释边界

- 授权检查依赖 SQLite 编译和 authorizer 行为，只覆盖原型支持的 SQL 范围；它不是 PostgreSQL 原生授权证明。
- D1 将基准参考 SQL 作为初始提案，不能用于估计真实数据智能体的越权率。
- 授权通过、SQL 执行成功和语义充分性是不同结果。除非另行进行人工审计，程序不会将语义状态标记为已验证。
- D3 使用冻结的合成案例，应与 D1 基准结果分开报告。
- API 调用可能产生费用，模型或服务版本变化也可能影响复现结果。

## 引用

- Klisura, Đ., Khoury, J., Kundu, A., Krishnan, R., & Rios, A. (2026). *Role-Conditioned Refusals: Evaluating Access Control Reasoning in Large Language Models*. Findings of EACL 2026. [ACL Anthology](https://aclanthology.org/2026.findings-eacl.316/)。
- Yu, T., Zhang, R., Yang, K., et al. (2018). *Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task*. EMNLP 2018. [Spider 项目](https://yale-lily.github.io/spider)。


## 复现状态

D1、D3 当前包含的实验材料、数据版本及发布注意事项见 [`docs/REPRODUCIBILITY_NOTES.md`](docs/REPRODUCIBILITY_NOTES.md)。

## 代码许可

当前仓库尚未提供本项目代码的许可证。若要以开源软件形式再分发代码，项目贡献者应先确认许可证并添加相应的 `LICENSE` 文件。外部数据仍受各自许可证约束。
