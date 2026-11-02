# RAG 评测数据集与 DeepEval

在侧栏「数据集」构建和维护单轮 RAG 评测样本。生成引擎直接使用 **DeepEval SDK 4.3.2 的 Synthesizer**，无需部署 DeepEval 服务或登录 Confident AI。评测执行、打分和结果对比尚未接入。

## 构建入口

- **数据集导入**：直接导入 CSV、JSON、JSONL，不调用模型；也可勾选「使用 AI 扩写已有数据集」，选择当前空间的种子数据集，调用 `a_generate_goldens_from_goldens`。仅使用启用的数据项；有参考上下文的种子和无参考上下文的种子需要分开。SDK 提取种子的问题风格，再结合空间提示词和任务要求生成。
- **从文档生成**：上传 TXT、Markdown、文本 PDF、DOCX、CSV，提取文本后调用 `a_generate_goldens_from_contexts`，生成问题、参考答案和参考上下文。扫描 PDF 需先 OCR。
- **从Dify知识库生成**：读取所选 Dify 配置中的知识库 ID 和 Dataset API Key，分页拉取已启用、未归档文档的可用分段，调用相同的 SDK 上下文生成流程。不会修改 Dify 内容。
- **空白数据集**：手动创建和编辑 Golden；也可勾选「使用 AI 按任务生成」，填写生成任务，调用 `a_generate_goldens_from_scratch`。无上下文生成仅产生问题，不编造参考答案。

目标大小为 1–500 条。生成模型和可选的质量评审模型均使用当前空间已经配置的端点与加密凭据；未选择质量评审模型时复用生成模型。空间设置提供默认构建模型及提示词，点击「恢复默认提示词」后保存可重置。提示词通过 SDK 的 `StylingConfig.task` 提供任务要求，输出结构由 SDK 控制；生成记录保存参数、模型和提示词快照。

## DeepEval 配置

「DeepEval 高级配置」支持：

- `FiltrationConfig`：质量阈值、质量评审次数上限、评审模型。
- `EvolutionConfig`：0–3 轮演化，七种演化方式的相对权重（0 禁用）。默认使用具体化、约束、比较，尽量保持资料依据；推理、假设、拓宽主题可能超出来源。多上下文演化需要多个片段；SDK 在无资料生成时忽略该演化方式。
- `StylingConfig`：生成任务、应用场景、问题风格、答案风格。种子扩写还会使用 SDK 的风格提取模板。
- 是否生成参考答案、每组上下文片段数量（1–5）、模型并发上限（1–10）。质量评审只适用于有上下文的生成流程。

SDK 达到评审次数上限后可能保留低分项。`additional_metadata.synthetic_input_quality`、`evolutions` 等 SDK 元数据原样保存，`additional_metadata.prismlab_generation` 补充来源、阈值及低分待复核标记。该分数评估的是演化前的问题，不代表最终答案正确性。生成结果仍应人工审阅。

文档当前沿用 PrismLab 的文本解析与约 4000 字符切分，Dify 使用现有分段；按顺序组合相邻片段，均匀选取来源生成。**尚未接入** SDK `generate_goldens_from_docs` 的 embedding 语义组块、文档质量选择，也未接入 `ConversationalGolden` 多轮对话。大知识库不保证每个片段都有对应问题。

## 标准 Golden 格式

以 SDK 的 `Golden` 模型作为字段和类型的唯一依据。JSON 导出是 `Golden.model_dump(mode="json")` 的记录数组，JSONL 每行一条，CSV 为同名列。支持 SDK 的 snake_case 字段及其 camelCase 序列化别名，保留完整单轮 Golden 字段：

```json
[
  {
    "input": "PrismLab 是什么？",
    "expected_output": "PrismLab 是 AI 模型测试与分析平台。",
    "context": ["PrismLab 是 AI 模型测试与分析平台。"],
    "additional_metadata": {"source": "product.md"},
    "source_file": "product.md",
    "expected_tools": [{"name": "search", "input_parameters": {"q": "PrismLab"}}],
    "expected_labels": {"intent": "product"},
    "expectations": {"must": ["回答基于资料"], "must_not": ["编造信息"]}
  }
]
```

`input` 为非空字符串，`expected_output` 为可空字符串。`context` 为参考上下文；`retrieval_context` 与 `actual_output` 用于记录实际系统结果，不能混作标准答案。还支持工具调用、comments、name、custom_column_key_values、token_cost 和 token 数等 SDK 字段。字段类型由 SDK 校验；未知字段和冲突别名会拒绝导入，避免静默丢失内容。

直接在 Python 中加载导出的 JSON：

```python
import json
from deepeval.dataset import EvaluationDataset, Golden

with open("dataset.json", encoding="utf-8") as f:
    dataset = EvaluationDataset(goldens=[Golden(**row) for row in json.load(f)])
```

JSON 导入也支持含 `goldens` / `items` / `data` 数组的对象。CSV 的 context / retrieval_context 沿用 SDK 的 `|` 分隔格式，也接受 JSON 数组；其他列表、对象使用 JSON 编码，并按 CSV 规则转义双引号。问题、答案是普通文本。CSV 无法区分空字符串与 null，且上下文中的 `|` 存在歧义，需要完整无损传输时请使用 JSON / JSONL。支持 UTF-8 和 GB18030 编码。

应用的 ID、时间戳和启用/归档状态属于管理信息，不进入 Golden 导出。导出包含所有数据项，归档状态不随标准格式传输；追加导入创建新本地 ID。导入的多模态映射不允许引用服务器本地文件；当前功能面向文本 RAG 数据。

## 旧数据兼容

旧 `reference_contexts` / `contexts` 转换为 `context`，`metadata` 转换为 `additional_metadata`，接受 `question` / `answer`、`user_input` / `reference`、`ground_truth` 别名。旧的对象或数组型问题、答案转换为 JSON 字符串；原始类型和值保存在 `additional_metadata._prismlab_legacy_values`，若该键已存在则使用额外下划线避免覆盖。

历史数据库 payload 在读取时兼容转换，原始记录保留；新增和编辑使用标准 Golden 字段。转换是幂等的，不重写历史资料或删除字段。旧内置提示词自动采用新的 SDK 任务提示词，自定义提示词保留。

## 进度、恢复与用量

后台按批次执行并保存结果，页面轮询进度。输出会经过 Golden 校验和忽略大小写/空白的完全重复检测，未达到目标条数会标记失败并保留已有结果，支持继续构建。服务重启也会标记未完成构建失败。重试沿用参数和提示词快照，读取当前凭据；文档和种子使用保存的来源快照，Dify 成功拉取后也保存快照，避免续建混用不同版本的资料。

记录模型请求次数及上游返回的输出 token 数；自定义端点缺少统一定价，费用为未知，不显示为零。上游未返回的用量和失败请求消耗可能不包含在 token 统计中。SDK 遥测关闭，异步生成结果仅保存在本应用，不自动上传 Confident AI。

每次上传最多 20 个文档 / 10 MB，提取文本总量最多约 200 万字符；Dify 文本量同样受限。每次导入最多 10 MB，每个数据集最多 20000 条，每条最多 200000 字符。文件全部验证后再写入；构建过程中支持查看、搜索和导出，编辑和删除需等待完成。删除数据集会一并删除其源文本及种子快照。

个人与团队的数据集、来源、默认模型和提示词按 PostgreSQL schema 隔离。团队成员可维护数据集及使用团队模型，仅所有者和管理员可修改空间默认配置。

## API

沿用登录、CSRF 和 `X-Workspace-Id` 空间上下文。接口参数见应用 API 文档。

| 路径 | 用途 |
| --- | --- |
| `GET/POST /api/datasets` | 分页搜索 / 创建空数据集 |
| `POST /api/datasets/import` | multipart：`name`、`description`、`file` |
| `POST /api/datasets/generate` | multipart：`name`、`description`、`options`（JSON）、`files` |
| `GET/PUT/DELETE /api/datasets/{id}` | 状态 / 修改名称描述 / 删除 |
| `POST /api/datasets/{id}/retry` | 继续未完成的构建 |
| `GET/POST /api/datasets/{id}/items` | 分页搜索 / 添加 Golden |
| `PUT/DELETE /api/datasets/{id}/items/{item_id}` | 替换 Golden 与状态 / 删除 |
| `POST /api/datasets/{id}/import` | 追加导入 |
| `GET /api/datasets/{id}/export?format=json` | `json` / `jsonl` / `csv` Golden 导出 |
| `GET/PUT /api/dataset-settings` | 默认构建模型和提示词，`prompt: null` 重置 |

`options` 示例：

```json
{
  "method": "contexts",
  "size": 50,
  "llm": {"id": "provider-config-id", "model": "model-alias", "credential_id": "credential-id"},
  "quality_threshold": 0.5,
  "max_quality_retries": 3,
  "num_evolutions": 1,
  "evolutions": {"CONCRETIZING": 1, "CONSTRAINED": 1, "COMPARATIVE": 1},
  "max_concurrent": 3,
  "context_size": 2,
  "include_expected_output": true
}
```

省略 `llm` 使用空间默认模型。`critic_llm` 使用相同选择结构。从 Dify 生成时传 `dify_config_id`、省略 `files`；种子扩写传 `method: "goldens"` 和 `seed_dataset_id`；无资料生成传 `method: "scratch"` 及非空 `task`，后两者均不上传文件。
