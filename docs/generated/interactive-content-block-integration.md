# Interactive Content Block Integration

> 版本：v0.2  
> 目标：把当前 `interactive-process` 原型能力收敛为 ai-shifu TokUI 课程设计中的互动图片教学活动  
> 状态：代码阅读后的产品与数据边界草案  
> 重要约束：ai-shifu 课程设计数据是 source of truth，`interactive-process` 的 JSON / sample / 独立编辑器都不能成为长期真数据。

## 1. 一句话结论

`interactive-process` 未来不应作为独立产品存在。第一阶段也不先新建一个通用 `Content Blocks[]` 系统，而是融合为 ai-shifu 现有 TokUI 课程设计中的一种特殊结构：

```text
Outline lesson
  -> DraftTokuiTemplate
      -> teacher_intent
      -> prompt_template
      -> material_refs
      -> media_refs
      -> interaction_points
      -> interactive_blocks[]
  -> PublishedTokuiTemplate snapshot
  -> LearnerTokuiArtifact
  -> hotspot-level learning records
```

其中第一版 `interactive image block` 是 TokUI 课程设计里的一个结构化互动活动：

```text
一张底图
多个圆点热点
每个热点绑定一个完整学习单元
学生完成全部热点和小测试后，互动块完成
完成结果写回 ai-shifu 学习记录
```

费曼式说法：

```text
ai-shifu 是课本。
TokUI template 是老师写给 AI 老师的教案。
互动图片活动是教案里的一段特殊课堂活动。
当前 interactive-process 是草稿纸和实验工具，不是最终课本。
```

## 2. 已定产品决策

### 2.1 产品身份

已定：

```text
interactive-process 的最终身份 = ai-shifu TokUI 课程设计中的互动图片教学活动
```

第一阶段采用：

```text
A. TokUI 课程设计的一种特殊结构
```

也就是说，互动图片活动和 `teacher_intent`、`prompt_template`、`material_refs`、`media_refs`、`interaction_points` 一样，都是“这一节课到底怎么教”的课程设计数据。

第一阶段不采用：

```text
独立互动项目
独立课件工作台作为长期主入口
只在学生端播放一份外部 JSON
把互动内容当成普通媒体资源
新建一套脱离 TokUI template 的通用 Content Blocks[] 课程系统
```

原因：

```text
互动块不是单纯图片、视频或播放器。
它是 lesson 中的一段学习活动，必须和课程设计、发布、学习记录绑定。
ai-shifu 现有代码已经有 DraftTokuiTemplate -> PublishedTokuiTemplate -> LearnerTokuiArtifact 这条链路。
第一阶段沿着这条路走，风险最低。
```

### 2.2 当前独立编辑器身份

已定：

```text
当前 interactive-process 独立编辑器只保留为临时原型 / 调试工具。
```

它可以继续用于：

```text
快速验证热点交互体验
验证底图、圆点、视频片段、讲解、依据卡、小测试的组合方式
辅助演示互动课件形态
```

但不能作为：

```text
长期正式编辑入口
课程数据 source of truth
学生端正式数据来源
产品验收的唯一依据
```

正式数据必须进入 ai-shifu 的课程设计数据结构。

### 2.3 第一版融合闭环

已定：

```text
第一版做 ai-shifu TokUI 课程设计里的最小互动图片编辑 + 学生端播放。
```

第一版不追求把独立 Studio 全量搬进 ai-shifu。  
先打通这条链路：

```text
老师在 ai-shifu lesson 的 TokUI 课程设计中添加 interactive image block
  -> 老师配置底图、圆点热点、视频时间段、讲解、依据卡、小测试
  -> 审核通过并发布
  -> 发布为 PublishedTokuiTemplate 快照
  -> 学生端 TokUI runtime 读取 published template
  -> 学生在 lesson 学习流中遇到互动图片活动
  -> 学生按顺序完成所有热点
  -> 学习记录写回 ai-shifu
```

### 2.4 代码阅读后的现有 ai-shifu 融合点

已确认的代码事实：

```text
DraftShifu / DraftOutlineItem
  -> 课程和 lesson 草稿

DraftTokuiTemplate
  -> 老师端 TokUI 课程设计草稿
  -> 已有 teacher_intent / prompt_template / material_refs / media_refs / generation_options / context_policy

PublishedTokuiTemplate
  -> 发布后的 TokUI template 快照
  -> 学生端 runtime 读取它，不读取老师草稿

LearnTokuiArtifact
  -> 某个学生实际生成和看到的 TokUI 学习内容

LearnTokuiResponse
  -> 学生提交的结构化回答记录
```

因此第一阶段的技术方向是：

```text
在 DraftTokuiTemplate / PublishedTokuiTemplate 承载 interactive_blocks 结构。
老师端在 TokuiTemplatePanel 附近提供互动图片设计器。
发布时把互动图片结构复制进 PublishedTokuiTemplate 快照。
学生端 TokUI runtime 读 published template 后渲染互动图片活动。
学生端记录必须细到 hotspot 级。
```

不应优先做：

```text
直接让 interactive-process JSON 进入学生端
在 standalone 项目里继续扩展正式课程数据
把互动图片塞成普通 media_refs
把所有热点、小测、完成记录压成一个普通表单回答
```

费曼式说法：

```text
DraftTokuiTemplate 是老师桌上的教案。
PublishedTokuiTemplate 是盖章发给课堂的正式教案。
LearnerTokuiArtifact 是学生这次上课真正看到的页面。
LearnTokuiResponse 和后续热点记录是学生交上来的答题纸。

互动图片不能只躺在草稿纸 interactive-process 里。
它必须被写进 ai-shifu 的正式教案，再进入学生课堂。
```

## 3. 第一版能力边界

### 3.1 底图

已定：

```text
一个 interactive image block 第一版只支持 1 张底图。
```

原因：

```text
第一版重点是融合进 ai-shifu 的课程数据和学生学习流，
不是复制 standalone Studio 的多场景能力。
```

不做：

```text
多场景图
场景跳转
状态图链路
任意流程图式互动
```

后续可以扩展：

```text
interactive image block v2
  -> 多场景
  -> 场景跳转
  -> 完成条件分支
```

### 3.2 热点

已定：

```text
第一版只支持圆点热点。
```

原因：

```text
圆点位置简单，编辑简单，不容易遮挡底图。
```

不做：

```text
矩形区域热点
多边形热点
复杂遮罩热点
```

后续扩展：

```text
如果真实教学中必须框选大面积结构，再增加矩形热点。
```

### 3.3 多互动块

已定：

```text
一个 lesson 的 TokUI 课程设计可以包含多个 interactive image block。
```

原因：

```text
lesson 是一节课，不是一张互动图。
一节课中可能有多个互动活动。
```

示例：

```text
Lesson: 道岔入门
  1. 文本导入：什么是道岔
  2. 视频说明：道岔整体作用
  3. Interactive Image Block：认识尖轨、基本轨、转辙机
  4. 文本总结：道岔为什么能改变线路
  5. Interactive Image Block：车轮路径辨认
  6. 小测试：道岔概念判断
```

### 3.4 学习流排序

已定：

```text
互动图片活动在 lesson 学习流中的顺序由老师手动控制。
```

原因：

```text
课程结构是老师设计的。
系统不应强行把互动块固定到最前或最后。
第一阶段即使数据放在 TokUI template 里，也必须保留顺序字段，不能让 runtime 随机摆放。
```

### 3.5 学生完成顺序

已定：

```text
多个互动图片活动按 lesson 学习流顺序完成。
```

第一版不做：

```text
自由跳转
老师配置是否强制顺序
AI 自动决定学习顺序
```

原因：

```text
新员工入门课需要稳定路径。
铁路概念有前后依赖，第一版先按老师设计的顺序学。
```

## 4. 互动块内容结构

### 4.1 Interactive Image Block

第一版互动图片活动作为 `DraftTokuiTemplate / PublishedTokuiTemplate` 中的 `interactive_blocks[]` 结构存在。

第一版结构包含：

```text
block_id
lesson_id
kind = interactive_image
title
description
display_order
base_image_resource_id
hotspots[]
status
published_version
created_by
updated_by
created_at
updated_at
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `block_id` | 互动块业务 ID |
| `lesson_id` | 所属 lesson / outline item |
| `kind` | 互动活动类型，第一版固定为 `interactive_image` |
| `title` | 互动块标题 |
| `description` | 老师端说明，可选 |
| `display_order` | 在 lesson 学习流中的排序 |
| `base_image_resource_id` | 底图资源 ID |
| `hotspots[]` | 圆点热点列表 |
| `status` | 草稿、待审核、已通过、需修改、已发布等状态 |
| `published_version` | 当前发布版本 |

字段存放原则：

```text
第一阶段不把它做成独立 standalone JSON。
第一阶段不优先新建一套通用 Content Blocks[]。
第一阶段让它成为 TokUI template 的结构化课程设计数据。
```

### 4.2 Hotspot

一个热点就是一个微课节点。

第一版热点包含：

```text
hotspot_id
block_id
label
position_x
position_y
video_resource_id
clip_start
clip_end
learning_objective
approved_explanation
evidence_cards[]
quiz
status
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `hotspot_id` | 热点业务 ID |
| `block_id` | 所属互动块 |
| `label` | 热点名称，如“尖轨”“转辙机”“基本轨” |
| `position_x` / `position_y` | 圆点在底图中的百分比位置 |
| `video_resource_id` | 授权视频资源 |
| `clip_start` / `clip_end` | 视频播放时间段 |
| `learning_objective` | 这个热点要学生学会什么 |
| `approved_explanation` | 审核后的固定讲解 |
| `evidence_cards[]` | 多条依据卡 |
| `quiz` | 单选或判断题 |
| `status` | 草稿、待审核、已通过、需修改 |

发布前，每个热点必须完整并已通过。

必填要求：

```text
热点名称
热点位置
绑定视频
视频开始时间
视频结束时间
学习目标
审核后的讲解稿
至少一条依据卡
一道单选 / 判断题
内容状态 = 已通过
```

### 4.3 学生端渲染决策

已定：

```text
学生端不把互动图片活动拆成普通 img + video + form 的松散组合。
TokUI runtime 可以负责把它带入课堂流，但前端应使用专门的 interactive-image 组件渲染。
```

推荐形态：

```text
PublishedTokuiTemplate.interactive_blocks[]
  -> learner runtime 生成/返回包含 interactive block 引用的课堂内容
  -> TokUI renderer 遇到 interactive-image 引用
  -> 专门组件渲染底图、热点、视频片段、讲解、依据卡、小测和完成状态
```

不推荐：

```text
让 LLM 临时用普通 TokUI DSL 拼出整套互动图
让热点坐标、完成状态、小测记录散落在普通文本或普通表单里
让学生端直接读取 interactive-process 导出的 JSON
```

原因：

```text
互动图片不是一张图加几个按钮。
它有内部状态：哪个热点点过、哪个热点视频看过、哪道热点题答过、整个互动活动是否完成。
这些状态必须由专门组件和专门记录来承接。
```

费曼式说法：

```text
普通 TokUI DSL 像积木。
互动图片活动像一个带机关的小模型。
可以把小模型放进积木课堂里，但不能把机关拆成一堆散件再指望它自己工作。
```

## 5. 视频素材规则

### 5.1 视频来源

已定：

```text
使用已授权视频。
```

授权视频可以本地保存到 ai-shifu 的资源系统中。

不依赖：

```text
外部平台链接长期可用
现场联网播放
外部平台广告和播放控件
```

### 5.2 视频时间段

已定：

```text
保留原视频文件，用时间点跳转，不强制切片。
```

老师在热点上配置：

```text
video_resource_id
clip_start
clip_end
```

示例：

```text
尖轨热点：
  视频：turnout_authorized_demo.mp4
  开始：00:35
  结束：00:55
```

说明：

```text
同一个授权视频可以被多个热点复用。
每个热点只播放和当前学习目标有关的片段。
```

### 5.3 时间点标注

已定：

```text
视频时间点由人工老师标注。
```

第一版不做：

```text
AI 自动识别视频内容
AI 自动切时间段
视频理解自动标注
```

原因：

```text
铁路专业视频中，尖轨、基本轨、转辙机、锁闭等概念容易被 AI 看错。
第一版以老师人工标点保证可靠性。
```

## 6. 依据卡与 RAG

### 6.1 资料来源

已定：

```text
RAG 资料库第一版使用：
1. 铁路规范 / 标准 / 教材
2. 院内培训资料 / 专家讲义 / 脱敏项目材料
```

不把以下资料作为权威判定层：

```text
网上科普文章
视频字幕
外部讲解口播
```

这些可以作为表达参考，但不作为最终正确性依据。

### 6.2 RAG 的角色

已定：

```text
RAG 主要服务内容生产者。
```

也就是说：

```text
老师和内容设计者用 RAG 确保讲解正确。
AI 可以基于 RAG 草拟依据卡。
老师审核后，学生端展示短摘要和来源。
```

不做：

```text
把规范全文直接砸给学生
让学生端依赖 AI 实时引用
学生点击热点后由 AI 现场生成主讲解
```

### 6.3 依据卡结构

一个热点可以绑定多条依据卡。

结构：

```text
evidence_card_id
hotspot_id
source_title
source_type
section_or_page
summary
detail_reference
review_status
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `source_title` | 资料名称，如某规范、某院内培训资料 |
| `source_type` | `standard` / `internal_training` / `textbook` / `project_material` |
| `section_or_page` | 章节、条款、页码或课件页 |
| `summary` | 给学生看的短摘要 |
| `detail_reference` | 老师端可展开的更详细依据信息 |
| `review_status` | 审核状态 |

学生端默认展示：

```text
资料名称
章节/页码
一句短摘要
可展开详情
```

示例：

```text
依据来源：《铁路轨道培训资料》第 12 页
摘要：本节只引用“尖轨与基本轨配合，引导车轮进入不同线路”这一教学点。
```

## 7. 讲解稿规则

### 7.1 学生端讲解必须固定

已定：

```text
学生端看到的讲解内容必须是审核后的固定内容。
```

不做：

```text
学生点击热点后，AI 实时生成主讲解
每次打开讲法都不一样
未审核 AI 讲解直接进学生端
```

原因：

```text
正式培训需要可控、可审核、可追溯。
AI 可以辅助备课，但不能不经审核站上讲台。
```

费曼式说法：

```text
AI 是帮老师备课的小助教。
学生看到的是老师确认过的讲义。
```

### 7.2 AI 的可选位置

AI 可以作为内容生产辅助：

```text
整理规范资料
草拟依据卡摘要
草拟费曼讲解稿
草拟单选 / 判断题
```

但必须经过：

```text
老师审核
状态通过
发布版本
```

才可进入学生端。

### 7.3 讲解风格

讲解稿应采用费曼风格：

```text
先说看哪里
再说发生了什么
再说为什么重要
最后用生活类比收束
```

示例：

```text
看这里，尖轨像一扇会移动的小门。
它贴住哪一边，车轮就会被带向哪一条线路。
所以尖轨的位置，会改变车轮的走向。
```

## 8. 小测试

### 8.1 题型

已定：

```text
第一版只支持单选题 / 判断题。
```

不做：

```text
开放问答
AI 自动批改
拖拽题
图上标注题
```

原因：

```text
第一版要稳定自动判分，不引入 AI 评判风险。
```

### 8.2 题目结构

```text
quiz_id
hotspot_id
question_type
question
options[]
correct_answer
explanation
```

示例：

```text
题目：转辙机直接推动的是哪一个部件？
A. 车轮
B. 尖轨
C. 轨枕

正确答案：B
解析：转辙机通过连杆推动尖轨移动，不是直接推动车轮。
```

## 9. 审核与发布

### 9.1 内容状态

互动块和热点内容支持状态：

```text
draft       草稿
pending     待审核
approved    已通过
needs_work  需修改
published   已发布
archived    已归档
```

学生端只读取：

```text
published version
```

老师端可预览：

```text
draft / pending / approved
```

### 9.2 发布前完整性

已定：

```text
发布前所有热点必须完整并已通过。
```

每个热点必须具备：

```text
视频时间段
审核后的讲解
至少一条依据卡
一道可判分小测试
```

不允许：

```text
空热点进入学生端
草稿内容进入学生端
未审核讲解进入学生端
```

## 10. 版本管理

### 10.1 发布后修改生成新版本

已定：

```text
互动内容块发布后，老师修改底图、热点、视频时间段、讲解、依据卡或测试题，都生成新版本。
```

不允许直接覆盖已发布版本。

原因：

```text
不能在学生答题记录下面偷偷换题。
要换题，就出新版试卷。
```

### 10.2 版本流

```text
Draft
  -> 审核通过
  -> Published Version 1
  -> 学生学习 Version 1

老师修改
  -> 从 Version 1 创建 Draft
  -> 审核通过
  -> Published Version 2
  -> 新学生学习 Version 2

旧学生记录仍然绑定 Version 1
```

### 10.3 版本字段

```text
block_version_id
block_id
version_number
snapshot_json
published_by
published_at
status
```

说明：

```text
学生端读取的是发布版本快照。
学习记录绑定发布版本，而不是绑定可变草稿。
```

## 11. 学生端流程

### 11.1 学习流中遇到互动图片活动

```text
学生进入 lesson
  -> 按 lesson 学习流顺序学习
  -> 遇到 interactive image block
  -> 显示底图和圆点热点
  -> 学生点击热点
```

### 11.2 热点学习顺序

一个热点点击后：

```text
1. 播放授权视频指定时间段
2. 展示审核后的费曼讲解
3. 展示短依据卡，可展开详情
4. 完成单选 / 判断题
5. 标记热点完成
```

顺序已定：

```text
视频片段 -> 讲解 -> 依据卡 -> 小测试
```

原因：

```text
先让学生看见。
再告诉他刚才看见了什么。
再告诉他为什么这说法靠谱。
最后让他自己判断一次。
```

### 11.3 互动块完成条件

已定：

```text
所有热点都点过，并完成每个热点的小测试。
```

每个热点完成条件：

```text
视频片段播放过
讲解展示过
小测试作答过
```

整个互动块完成条件：

```text
所有热点完成
```

## 12. 学习记录

### 12.1 必须写回 ai-shifu

已定：

```text
互动块完成结果必须写回 ai-shifu 学习记录。
```

原因：

```text
互动块不是网页上的小玩具。
它是课程任务。
学生做没做、做对没做对，ai-shifu 必须知道。
```

### 12.2 记录粒度必须到热点级

已定：

```text
第一版学习记录必须做到 hotspot 级。
```

必须能回答：

```text
学生点了哪个热点？
这个热点的视频片段是否看过？
这个热点的讲解是否看过？
这个热点的小测答了什么？
这个热点的小测是否答对？
这个互动图片活动是否整体完成？
```

建议记录结构：

```text
learner_id
lesson_id
block_id
block_version_id
hotspot_id
quiz_id
video_viewed
explanation_viewed
answer
is_correct
started_at
completed_at
```

这样可以回答：

```text
学生完成了哪个版本的互动块？
学生点了哪个热点？
学生哪道题答错了？
学生是否完整完成该互动学习活动？
```

不接受的记录粒度：

```text
只记录 interactive image block 完成 / 未完成
只记录一个普通 TokUI field_id 的笼统答案
只把所有热点结果塞成一段无法查询的文本
```

原因：

```text
铁路培训需要知道学生到底卡在哪个结构点。
如果只记总完成，老师无法判断学生是没看懂尖轨、转辙机、辙叉，还是只是某一道题选错。
```

## 13. 与当前 interactive-process 原型的关系

### 13.1 可复用的能力

当前原型中可作为未来能力参考：

```text
底图 + 热点渲染
圆点热点视觉
视频片段播放体验
热点点击后的内容面板
隐藏/显示热点
本地导入导出作为调试能力
端到端浏览器验证思路
```

### 13.2 不直接继承为产品真相的部分

不能把以下内容当成长期正式方案：

```text
独立项目 JSON 作为课程真数据
独立 Studio 作为唯一编辑入口
frontend sample / fixture 作为课程内容来源
只在前端 localStorage 保存课程
只靠导入导出 zip 管理正式课程
```

### 13.3 正式融合原则

```text
ai-shifu backend owns data
teacher/admin UI edits persisted course design
student runtime reads published course content
learning records are persisted in ai-shifu
interactive-process is component/prototype knowledge, not source of truth
```

## 14. 明确排除项

第一版不做：

```text
AI 实时讲解主课内容
AI 自动理解视频并标时间点
AI 自动批改开放问答
AI 生图 / AI 视频作为主线内容生产方式
多场景互动图
矩形 / 多边形热点
复杂分支流程
学生自由跳过学习流顺序
草稿内容进入学生端
```

这些可以作为后续研究项，但不进入第一版融合目标。

## 15. 最小闭环验收

第一版融合成功的标准：

```text
老师可以在 ai-shifu lesson 的 TokUI 课程设计中添加 interactive image block。
老师可以上传/选择一张底图。
老师可以添加多个圆点热点。
每个热点可以绑定授权视频和开始/结束时间。
每个热点可以填写审核后的讲解稿。
每个热点可以绑定多条依据卡。
每个热点可以配置一道单选/判断题。
发布前系统校验所有热点完整并已通过。
发布后生成不可变版本。
学生端按 lesson 学习流顺序看到互动图片活动。
学生端由专门 interactive-image 组件渲染底图、热点和热点学习流程。
学生点击热点后按固定顺序学习：视频片段、讲解、依据卡、小测试。
学生完成所有热点后，互动块完成。
学习记录写回 ai-shifu，并且必须绑定 block version、hotspot、quiz。
```

最重要的验收原则：

```text
课程内容来自 ai-shifu 持久化课程设计。
学生学习记录写回 ai-shifu。
不依赖 interactive-process 独立 JSON 作为正式数据来源。
不依赖 frontend sample / fixture 作为课程真数据。
不只记录互动块总完成状态，必须保留热点级学习证据。
```
