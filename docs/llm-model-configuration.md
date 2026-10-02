# LLM 模型定义与请求参数方案

状态：Playground 的 YAML 动态参数、后端校验、供应商字段映射及只读能力刷新已接入运行时；测试计划、CLI、AI 报告参数复用与运行快照仍属于后续设计。下面的完整 schema 示例是架构建议，当前可执行 schema 见 `config/llm-models.yaml`。

## 当前使用方式

- 所有 7 个 LLM provider 通过同一个参数模块提供基础参数（max_tokens、temperature、top_p）。未知模型不会按名字猜测思考能力，界面明确显示基础兼容配置。
- Playground 选择模型后动态生成表单，思考模式与 effort/budget 联动；未设置的可选参数不发送，使用服务默认。max_tokens 默认 256，应用侧上限为 8192，服务较小的上限会进一步约束它。
- DeepSeek、硅基流动、vLLM、阿里云和 Xinference 的已明确列出的混合思考模型有对应 YAML 参数映射。思考参数不是所有模型或所有部署都支持，实际 UID 必须与 YAML 中 provider + patterns 精确匹配。
- 「刷新模型能力」只对已接入模型列表接口的 DeepSeek、硅基流动、vLLM、Xinference 开放，只请求 GET /models，不生成文本、不自动保存模型配置；缓存有效期 1 小时，按供应商、端点、模型 UID 和凭据隔离。服务未返回字段时保持未知，失败不覆盖已有表单。
- DeepSeek 官方返回的 effort 档位可以覆盖 YAML 档位；其他供应商未声明字段映射时不自动开启此能力。服务容量元数据可补充 YAML，系统安全上限不被放宽。
- 流式思考内容折叠展示，答案独立显示；TTFT 仍是首个任意输出，TPOT/tokens/s 仍按服务报告的总输出 token 计算，界面明确注明口径。原始结果包含本次显式参数与能力定义版本，但 Playground 不创建持久运行记录。

新增本地部署 UID 时，在 `models` 中加入一条明确规则，例如：

```yaml
  - provider: vllm
    patterns: [my-qwen-deployment]
    profile: qwen_template
    metadata:
      context_window: 32768
      max_output_tokens: 8192
```

只有确认部署聊天模板支持 enable_thinking 时才能使用该 profile。其他模型可以新增 profile，配置参数类型、范围、提示语、依赖和允许的 api_field；认证、messages、model、stream 等受控字段不能被 YAML 或请求覆盖。修改 YAML 后新请求会重新读取，无需改 React 代码。

## 结论

建议「YAML 定义模型能力 + SQLite 保存部署配置和用户默认值 + 每次运行保存实际参数快照」。不要把所有供应商、模型和参数写死在 React/Python 中，也不要把 API Key 或每一次测试计划移入 YAML。

参数描述不是推理客户端：使用一个统一模块隐藏能力解析、校验、默认值合并和请求字段转换，所有调用方都通过同一个 interface 使用它。不要为 Playground、CLI、测试计划、AI 报告分别写一套 provider 判断。

## 三类不同的数据

| 层级 | 示例 | 保存位置 / 行为 |
| --- | --- | --- |
| 模型能力 | 支持思考、支持的 effort 档位、上下文上限、最大输出长度、模态 | 版本化 YAML；服务声明的能力可导入，并保留来源与获取时间 |
| 部署与用户默认值 | 实际模型 UID、端点、凭据、部署上下文限制、默认 thinking/effort | 现有 SQLite 模型配置；密钥继续加密，不写入 YAML |
| 单次请求参数 | 思考模式、effort、温度、最大输出 tokens、Prompt | Playground 或测试计划设置；运行创建时解析并持久化不可变快照 |

「支持深度思考」属于能力声明；「这次开启深度思考」属于请求参数。不要只使用一个布尔值混合两者。

**上下文窗口不是通用请求参数。** 模型容量与实际部署限制可能不同，尤其是本地 vLLM。可允许配置较小的部署上限，但不能据此宣称模型容量变大，也不应把 `context_window` 直接塞到 chat/completions 请求中。用匹配模型的 tokenizer 校验输入 + 输出预算；tokenizer 不可用时只能提示估算，不假装精确。不默认静默截断用户输入。

## 建议的 YAML 形状

以下只是未来 schema 的示例，不是当前可执行配置。DeepSeek 信息按 2026-10-02 的官方文档整理；模型别名及服务上限可能变化，应优先获取可验证的服务声明。

```yaml
schema_version: 1
models:
  - definition_id: deepseek/deepseek-flash
    provider: deepseek
    model_id: deepseek-flash
    label: DeepSeek Flash
    adapter: deepseek_chat_completions
    metadata:
      source: https://api-docs.deepseek.com/api/list-models/
      verified_at: 2026-10-02
      context_window_tokens: 1048576
      max_output_tokens: 393216
    capabilities:
      stream: true
      thinking: true
      input_modalities: [text, image]
      output_modalities: [text]
    parameters:
      thinking_mode:
        type: enum
        values: [enabled, disabled]
        default: enabled
        label: 思考模式
      reasoning_effort:
        type: enum
        values: [low, high, max]
        default: high
        enabled_when: {thinking_mode: enabled}
        label: 思考强度
      max_tokens:
        type: integer
        min: 2
        max_from: metadata.max_output_tokens
        default: 256
        label: 最大输出 token 数
```

YAML 用于声明而非执行代码：只允许已定义的类型、枚举、数值范围、有限依赖条件和白名单 adapter ID；使用 safe loader + 强类型 schema，禁止 eval、任意 Python 标签、自定义脚本和网络地址读取。模型上限与应用安全上限取较小值，不因 YAML 放宽模型侧或系统侧限制。

## 解析、校验与映射

建议对调用方只暴露 `resolve_llm_request(model_selection, request_overrides) -> resolved_request`：返回经过校验的请求 JSON、实际参数、能力来源和定义版本/hash。敏感访问凭据在发送时另行注入，不混入快照。

合并顺序：模型定义默认值 → 部署/用户默认值 → 本次计划或请求覆盖。能力与上限不是可任意覆盖的默认值。显式设置“不支持”或“在当前模式不生效”的参数应报错；自动继承的非适用默认值可以不发送并记录原因。切换模型时重新校验，不保留另一模型的非法 effort 档位。

不同供应商存在真实差异，必须保留小型 adapter：例如统一参数 `thinking_mode` 在 DeepSeek Chat Completions 中映射到 JSON `thinking.type`；其他服务可能使用其他字段或固定模型模式。不要把 `reasoning_effort` 简单视作所有模型都支持的统一枚举，也不要把 SDK 的 `extra_body` 当成 HTTP JSON 字段发送。

YAML 管「有哪些能力、参数和约束」；代码管「协议、流式解析、认证、错误处理与安全校验」。保留 model/messages/stream 等受控字段，禁止任意参数覆盖认证、端点或客户端强制的流式测量选项。

DeepSeek 的思考模式默认开启，推荐 effort 为 low/high/max；temperature、presence_penalty、frequency_penalty 在思考模式不生效，top_p 又有模式相关限制。这类交叉约束需要在能力定义与校验模块中明确表达，不能只画几个固定下拉框。

## 界面与可复现性

- 模型配置：显示能力、上下文/输出上限、定义来源与版本；可修改该部署的默认参数，不修改内置能力文件。
- Playground：选择模型后显示适用参数，常用参数在主表单，其余收进「高级参数」，同时显示服务默认与显式设置的区别。
- 测试计划：支持公共参数及每个模型的覆盖，便于比较多个模型；不同 effort/思考模式须作为不同实验条件，不混合在同一曲线中。
- AI 报告：默认分析模型也引用同一解析模块，避免报表生成与 Playground 的默认设置不一致。
- 运行记录：持久化模型实际 UID、能力定义版本/hash、最终生效参数、测量口径；配置或 YAML 后续改变不修改已创建运行。
- 分析看板：只有工作负载、输出预算、思考模式/effort 等条件可比时才合并或对比；条件不同应分组并明确标注。

## 思考模式下的指标口径

当前流式客户端将 reasoning_content 与 content 合并，并以第一段任意输出计算 TTFT；这不能直接称为「首个答案 token 的延迟」。后续应分开两条输出通道，折叠展示思考内容，单独定义首个输出、首个答案、思考阶段耗时。

TPOT / tokens/s 必须标注使用总输出 token 还是仅答案 token。仅在供应商报告对应 token 用量时计算；不能把 SSE chunk 数当 token 数，也不能用最终答案字符数假装 tokenizer。没有推理/答案细分用量时不显示“仅答案速度”，不把思考成本隐藏掉。

## 分阶段落地

1. 先做模型定义 loader、schema、adapter 与单元测试；未知模型使用保守的 OpenAI-compatible 基础能力，不按名字猜支持思考。
2. 接入 Playground，支持 thinking、effort、max_tokens，验证真实请求字段和未知参数错误；分离 reasoning/content 及测量口径。
3. 接入模型默认值、计划每模型覆盖、CLI 和运行快照；保持旧计划原有参数含义。
4. 最后接入 AI 报告与图表按实验条件分组，并允许从服务模型列表手动导入能力；同步不自动覆盖用户配置。

## 依据

- [DeepSeek 模型列表与能力元数据](https://api-docs.deepseek.com/api/list-models/)
- [DeepSeek 思考模式及参数限制](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)
- 项目现状：`shared/providers.py`、`backend/schemas.py`、`shared/llm_stream.py`、`backend/runner.py`、`frontend/src/components/Playground.tsx`。
