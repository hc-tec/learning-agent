# TokUI Prompting Guide

## 背景结论

TokUI 当前没有内置的大模型 system prompt 或官方 skill。根据项目源码与
issue 讨论，实际接入方式是：把 TokUI DSL 规则整理成 system prompt，随
LLM API 请求一起传入，让模型只输出 TokUI DSL。

可参考的上游材料不是隐藏 prompt，而是这些文件：

- `demo/TOKUI_DSL_REFERENCE.md`
- `docs/en/guide/dsl-syntax.md`
- `src/server/tokui-builder.js`
- `demo/server/sse-server.js`
- `src/core/parser.js`

其中 `tokui-builder.js` 最接近“官方推荐写法”，因为 demo 服务端就是用它链式
生成 DSL，再通过 SSE 分块输出。

## 接入建议

对学习产品来说，TokUI 不应该一次性开放全部 150+ 组件给模型。更稳的做法是
按场景约束组件子集：

- 普通解释：`card`、`h3`、`p`、`callout`、`code`、`quick-reply`
- 表单交互：`card`、`form`、`input`、`radio`、`select`、`checkbox`、`ft`、`btn`
- 报表数据：`card`、`stat`、`chart`、`table`、`thead`、`tbody`、`tr`、`callout`
- 对话教学：`bubble`、`think`、`p`、`source`、`suggestions`、`suggestion`

shadcn/ui 适配层面，prompt 不需要让模型“生成 shadcn”。模型只负责输出 TokUI
DSL；视觉统一由 `tokui-shadcn.css` 解决。也就是说：

```text
shadcn/ui = 应用外壳、固定页面、教师端/后台端
TokUI DSL = AI 生成的课程内容、对话内容、练习组件
tokui-shadcn.css = 把 TokUI 的视觉变量映射到 shadcn tokens
```

## Base System Prompt

下面这份 prompt 已用于 DeepSeek `deepseek-v4-flash` 实测，能显著减少 HTML
式属性、错误表格标签、错误闭合叶子标签等问题。

```text
You generate TokUI DSL for a learning application.
Return only TokUI DSL. No markdown fences, no prose, no HTML, no XML.

Core syntax:
- Use bracket tags: [card tt:"Title"]...[/card], [p Plain text], [btn tx:Continue v:primary].
- Attributes use key:value, never key="value". Quote values that contain spaces, colons, brackets, semicolons, or commas.
- Containers must close: card, ft, row, col, table, tbody, code, md, callout, steps, bubble, think, suggestions.
- Leaf tags do not close: h1-h6, btn, input, source, suggestion, step, chart with inline d, thead with cols, tr.
- Paragraph has two modes: plain text uses leaf [p Text] with no [/p]; block children use [p]...[/p].
- Use callout as [callout t:info tt:"Tip"]...[/callout] or [callout t:info tx:"Tip text"]. Do not invent attrs like tip:Text.
- Use table shorthand: [table][thead cols:"Name,Score"][tbody][tr Alice,90][/tbody][/table]. Never use th or td.
- Use form choice shorthand: [radio n:q1 l:"Question" opt:"a:Option A;b:Option B"]. Do not output [opt]...[/opt].
- Use chart shorthand: [chart t:scatter l:"1h,2h,3h" d:"55,65,80"].
- Avoid literal [ or ] in normal text. Use parentheses for arrays, e.g. (1, 3, 5). Brackets are allowed inside code/md raw containers.
- Avoid ASCII Q: or A: prefixes in body text; use full-width Q： or quote the body.
- If using think, write a brief visible reasoning summary only. Do not reveal hidden chain-of-thought.
```

## Form Prompt Case

适合“生成练习表单、注册表单、小测验”等交互型内容。

```text
Create one TokUI form card for a beginner programming quiz.
Return TokUI DSL only.
Use only these tags: card, form, input, radio, select, checkbox, ft, btn, p.

Rules:
- Use key:value attrs, not equals attrs.
- Prefer option shorthand for radio/select: opt:"value:Label;value2:Label2".
- Do not output [opt]...[/opt].
- Put submit/reset buttons inside [ft]...[/ft].
- Use named handlers only: sub:submitQuiz, clk:resetQuiz.

Shape:
[card tt:"Quiz"]
[form id:quizForm sub:submitQuiz]
[input n:name l:"Name" ph:"Your name" req]
[radio n:q1 l:"Question" opt:"a:Option A;b:Option B"]
[ft][btn tx:Submit v:primary][btn tx:Reset][/ft]
[/form]
[/card]
```

## Report Prompt Case

适合“生成学习报告、数据分析、阶段复盘”等内容。

```text
Create one TokUI report card about weekly learning progress.
Return TokUI DSL only.
Use only these tags: card, h3, p, stat, chart, table, thead, tbody, tr, callout.

Rules:
- Table syntax must be [table][thead cols:"Metric,Value"][tbody][tr Hours,12][/tbody][/table].
- Never use th or td.
- Chart with inline data is a leaf tag and must not close.
- Use chart shape [chart t:line l:"Mon,Tue,Wed" d:"30,45,60"].
- Avoid square brackets in text.
```

## Conversation Prompt Case

适合“AI 教师回复、苏格拉底式引导、引用来源、推荐下一步”等内容。

```text
Create one AI tutor response about recursion.
Return TokUI DSL only.
Use only these tags: bubble, think, p, source, suggestions, suggestion, quick-reply.

Rules:
- Use [bubble role:ai]...[/bubble].
- [think] is a short visible plan summary for the learner, not hidden chain-of-thought.
- Do not use markdown fences.
- source and suggestion are leaf tags; do not close them.
- Use [suggestions][suggestion tt:Trace tx:"Try factorial(3)" clk:trace][/suggestions].
```

## Lesson Prompt Case

适合“课程片段、知识点讲解、步骤说明、可继续追问”等内容。

```text
Create a three-step mini lesson about binary search.
Return TokUI DSL only.
Use only these tags: card, steps, step, p, callout, code, quick-reply.

Rules:
- step is a leaf tag in current TokUI docs. Use [step tt:"Step 1" desc:"Find the middle"].
- Never write [/step].
- Do not put p/callout/code inside step.
- Put detailed explanation after the closed steps block.
- In normal text, write arrays with parentheses like (1, 3, 5), not square brackets.

Shape:
[card tt:"Binary Search"]
[steps v:2][step tt:"Step 1" desc:"Find middle"][step tt:"Step 2" desc:"Choose half"][/steps]
[p Explanation text]
[code lang:python]...[/code]
[quick-reply items:"Trace it|Show code|Quiz me"]
[/card]
```

## Common Failure Modes

这些是 DeepSeek 实测中真实出现过的问题，需要靠 prompt、校验、重试兜底：

- 输出 HTML/XML 风格属性：`value="200"`，应为 `v:200` 或 `opt:"200:OK"`。
- 使用不存在的表格标签：`[th]`、`[td]`，应使用 `thead cols:"..."` 和 `[tr ...]`。
- 错误闭合叶子标签：`[/btn]`、`[/source]`、`[/suggestion]`、`[/step]`。
- 把 `callout` 写成伪属性：`[callout tip:Text]`，应使用 `t:info`、`tt:`、`tx:`。
- 普通正文出现 `Q:`、`A:`，会被 parser 当成属性，建议改成 `Q：` 或引号包裹。
- 普通正文出现数组方括号，比如 `[1, 2, 3]`，会被 parser 误判成标签。
- 在 `think` 中输出隐藏推理链。产品中应要求“可见计划摘要”，不要让模型泄露 chain-of-thought。

## Validation

已经加入一个本地校验脚本：

```powershell
node scripts\validate_tokui_outputs.mjs docs\generated\tokui-deepseek-benchmark-prompt-v5.json
```

它会读取 benchmark JSON，调用上游 TokUI parser，并检查：

- 是否有 markdown code fence
- 方括号是否平衡
- 是否出现 HTML 表格标签
- 是否出现疑似 equals 属性
- 是否闭合了叶子标签
- parser 是否报未匹配闭合标签
- 是否出现明显非法 tag type

建议后续 API 接入流程：

```text
LLM streaming output
→ 增量展示
→ 完整输出落库前 parser 校验
→ 校验失败时用 repair prompt 修复
→ 修复失败时降级为 markdown/card 文本
```

## DeepSeek Benchmark Notes

使用 `.env` 中的 `DEEPSEEK_API_KEY`，以 `deepseek-v4-flash` 做过流式实测。
最新 prompt v5 的一次 5 场景测试结果：

- total runs: 5
- successful runs: 5
- avg TTFB: about 209 ms
- avg first content/tag: about 668 ms
- avg total generation: about 2108 ms
- avg throughput: about 213 chars/sec
- code fence runs: 0
- unbalanced bracket runs: 0
- equals attr runs: 0
- html table tag runs: 0
- invalid leaf closing runs: 0
- parser validation: 5/5 passed

对应文件：

- `scripts/benchmark_tokui_deepseek.py`
- `scripts/validate_tokui_outputs.mjs`
- `docs/generated/tokui-deepseek-benchmark-prompt-v5.json`

## Recommendation

TokUI 可以继续用，但必须把“提示词 + 组件子集 + parser 校验 + repair retry”作为
基础设施的一部分，而不是只把 DSL 文档塞给模型后裸跑。

第一阶段建议只开放学习产品最需要的 20 到 30 个组件。等课程生成稳定后，再逐步
放开 chart、artifact、canvas、form action 等更高风险组件。
