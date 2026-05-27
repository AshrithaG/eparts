# eParts 数据交付评估报告

**评估对象：** `the_standard_data/` 目录下 2026-04-16 收到的 5 个文件
**对照基准：** [ML_Model_Proposal_and_Data_Requirements.md](ML_Model_Proposal_and_Data_Requirements.md) 第 5 节 Data Requirements
**评估方法：** Python / pandas 全量或分块读取，统计行数、空值率、唯一值、覆盖度

---

## 一、总体结论（TL;DR）

| 我们要求的 | eParts 交付的 | 评估 |
|---|---|---|
| **P1-A** 输入-输出配对样本 ≥ 200 对 | 1A_Product_Attribute_Pairs.csv — 1.94M 行 / 13.4 万产品 / 348 属性 | ✅ 数量满足；⚠️ 性质有落差（非客户原文） |
| **P1-B** 产品主表（含描述） | 1B_Product_Master.csv — 19.8 万行全目录 | ✅ 基本满足；⚠️ Product_Name 字段几乎全空 |
| **P2-A** 每属性合法取值清单 | 2A_Values_Per_Attribute.csv — 9,918 行 / 346 属性 | ✅ 满足，且额外提供了 Usage_Count |
| **P2-B** 历史错误/边界案例 ≥ 50 条 | 2B_Apparent_Correction_Cases.csv — 74.7 万行 | ❌ **不满足** —— 详见第四节 |
| **P3-A** 客户提交模板 | 未交付 | ❌ 未交付 |
| **P3-B** 各品类请求量分布 | 未交付 | ❌ 未交付 |
| — | 1A_Product_Document_Links.csv — 51.6 万条文档链接 | 🎁 **超额** —— 提供了 spec sheet 原件 URL |

**一句话判断**：建模层面（Layer 2 规则 + Layer 3 语义）的训练数据已经充足；但**错误案例和客户原始文本两大类"用来让模型学会承认自己不确定"的数据依旧缺失**。

---

## 二、符合需求的部分（逐项核对）

### 2.1 P1-A — 输入-输出配对样本 ✅

**Proposal 原文要求：**
> 200 pairs to start. More is always better. 每个样本包含 Source type、Raw input text、Verified correct output (Manufacturer / Product_ID / Attribute mappings)。

**交付：** `1A_Product_Attribute_Pairs.csv`

| 指标 | 数值 |
|---|---|
| 总行数 | 1,938,426 |
| 唯一 Product_ID | 134,117 |
| 唯一 Attribute_Name | 348 |
| Short_Description 非空率 | 99.8% |
| Extended_Description 非空率 | 78.1% |
| Full_Description 非空率 | 2.0% |

**字段构成**：`Product_ID, Product_Number, Manufacturer_Name, ProductType_Name, Short_Description, Full_Description, Extended_Description, Attribute_Name, Attribute_Value, DisplayText, Unit_Suffix, DigitalValue, RangeLow, RangeHigh`

**判断**：
- 数量上 **约为最低要求的 10,000 倍**，远超 PAC 下界 830 条的理论最小值。
- 字段比我们要的还全：额外提供了 `DigitalValue` / `RangeLow` / `RangeHigh`，这让 Layer 2 规则引擎处理数值范围型属性（温度、电压、流量）时可以直接用结构化数据，而不用从描述里正则抓。
- 同一个 Product_ID 对应多条记录（每条一个属性），符合文档字典说明的 "multiple values per attribute possible"。

### 2.2 P1-B — 产品主表 ✅（有一项瑕疵，见第四节）

**Proposal 原文要求：**
> `Product_ID | Part_Number | Product_Name | Description (free text) | Manufacturer_ID | Category_ID`

**交付：** `1B_Product_Master.csv` — 198,147 行（与 Data Dictionary 的 198,465 active products 几乎完全一致）

| 字段 | 非空率 |
|---|---|
| Product_ID / Product_Number / Product_Number_Custom | 100% |
| Manufacturer_ID / Manufacturer_Name | 100% |
| ProductType_ID / ProductType_Name | 100% |
| Category_ID | 100% |
| **Short_Description** | **99.9%** |
| Extended_Description_Pre | 84.2% |
| TarriffCode | 61.1% |
| Full_Description | 1.5% |
| Extended_Description_Post | 3.9% |
| **Product_Name** | **0.003%（仅 6 行）** ⚠️ |

**判断**：主键和分类信息 100% 完整；描述字段 99.9% 有内容（以 Short_Description 为主）。Product_Name 字段几乎全空这件事见第四节。

### 2.3 P2-A — 每属性合法取值 ✅+

**Proposal 原文要求：**
> 完整的属性-值清单，用于约束输出、避免模型预测数据库里不存在的值。

**交付：** `2A_Values_Per_Attribute.csv` — 9,918 行

| 指标 | 数值 |
|---|---|
| 唯一 Attribute_Name | 346 |
| 每属性平均合法值数 | 28.7 |
| 每属性合法值数中位数 | 7 |
| 取值最多的属性 | `ACCESSORY TYPE` (891 个值) |
| Usage_Count 最大值 | 45,231 |
| 空值行占比 | 4.8% |

**判断**：
- **亮点**：多给了一列 `Usage_Count`——这让我们能在 k-NN 和 Mahalanobis 打分时做**频次加权先验**（常见值拿更高先验，冷门值更保守），这是 Proposal 没要求、但对落地效果很有价值的字段。
- 4.8% 空值行需要在预处理时过滤（可能代表"该属性允许空/未知"这种情况）。
- 属性数量 346，而 Data Dictionary 写的是 487 个 active 属性——差 141 个。这意味着 **约 29% 的 active 属性在现有产品库里没有任何实际取值**，可能是新增或极罕见。

### 2.4 超额交付 🎁 — 产品文档链接

**交付：** `1A_Product_Document_Links.csv` — 516,005 条

| 指标 | 数值 |
|---|---|
| 有文档/图片的产品数 | 178,194 |
| PDF 文档 (ImageFile=0) | 339,412 |
| 图片 (ImageFile=1) | 176,593 |

**判断**：这是 Proposal 没要求但极其有用的超额内容。
- 可以直接驱动 Layer 1 的 OCR pipeline 做**端到端测试**：从真实 spec sheet PDF 出发 → OCR → 规则+语义 → 对比 1A 的验证答案。
- 可以用于**生成合成的"客户原始输入"**：因为我们缺真实客户邮件，可以从 PDF 抽取片段、模拟"只摘了一部分规格"的邮件请求。

---

## 三、做得特别好的地方

1. **数量规模远超预期。** 我们算的 PAC 下界只要 830 条，实际给了 1.94M 条属性对，让我们能做**按 ProductType 分层训练**、**冷门品类单独加权**这类更精细的操作。

2. **结构化字段多给了一层。** `DigitalValue` / `Unit_Suffix` / `RangeLow` / `RangeHigh` 让数值型属性（温度、压力、电压、流量）不必从自由文本再抽一遍，规则引擎 Layer 2 的置信度可以直接到 1.0。

3. **Usage_Count 作为频率先验。** 2A 提供的使用次数分布意味着我们不用从 1A 反推取值频次，可以直接用它做 Bayesian 先验，提升冷启动阶段的预测稳定性。

4. **spec sheet 原件 URL（1A-Links）。** 这是"超纲"交付。原本我们只要描述文本的配对，结果他们给了端到端可追溯到源材料的 URL，对系统评测和后续客户场景模拟都是加分项。

5. **Data Dictionary PDF 质量高。** 字段含义、表间关系、主外键约束、"三处逻辑连接但没有 FK 约束"这类暗坑都写清楚了，省掉我们大量逆向工程时间。

6. **ID / 分类字段 100% 完整。** `Product_ID`、`Manufacturer_ID`、`ProductType_ID`、`Category_ID` 无一缺失，join 操作不会遇到孤儿行（除了字典里标注的三处非强制 FK）。

---

## 四、仍不符合需求 / 存在问题的地方

### 4.1 ❌ **P2-B 错误案例——严重不符合**（最关键问题）

**我们的要求：** 50+ 条真实的"误判样例"——模型初判错误、人工复核纠正的案例，用来教模型识别**自己的知识边界**。

**交付物的真实情况：**

| 指标 | 数值 | 说明 |
|---|---|---|
| 总行数 | 746,845 | 看起来很多 |
| 唯一 EO_ID | **仅 6 个** | 所谓"Edit Order"只有 6 次 |
| 唯一 Product_ID | 25,203 | 其中 291 个产品有 > 1 次 EO 事件 |
| Edit_Count 中位数 | 2,685 | **这不是"每个产品被编辑过几次"，而是"该 EO 批次操作了多少产品"** |

**6 个 EO_Reason 的分布：**

| EO_Reason | 行数 | 占比 |
|---|---:|---:|
| `test` | 433,249 | 58.0% |
| `changing vendor` | 144,340 | 19.3% |
| `Flipping Air Products Vendor` | 144,340 | 19.3% |
| `HW - MORE DISABLE` | 14,706 | 2.0% |
| `HW - POWER METERS - DISABLE` | 10,205 | 1.4% |
| `ONICON - AMAZON PROJECT` | 5 | 0.001% |

**问题剖析：**
- readme 提示 "Products with Edit_Count > 1 were re-edited (likely corrections)"——但实际上 **Edit_Count 是每个 EO 影响的产品数**，不是每个产品的编辑历史次数。真正在多次 EO 里出现过的产品只有 **291 个**，而不是几十万。
- 6 个原因里没有任何一个语义上属于"模型应该学到的错误修正"：
  - "test" 是测试性批量操作
  - "changing vendor" / "Flipping Air Products Vendor" 是供应商切换（业务运营）
  - "HW - DISABLE" / "POWER METERS - DISABLE" 是下架
  - "ONICON - AMAZON PROJECT" 是项目标签
- 没有任何一条写的是"属性值填错了"、"品类分错了"、"型号歧义"这类我们真正需要的信息。

**结论：** 2B 文件**实际上无法用于训练置信度校准**。

### 4.2 ⚠️ P1-B 的 Product_Name 字段基本为空

`Product_Name` 字段在 19.8 万行里只有 **6 行**非空（0.003%）。

**影响：**
- Proposal 里我们列的示例格式是 `Product_Name = "Belimo Spring Return Actuator"` 这种可读的产品名。
- 现在只能用 Short_Description 顶替，后者是拼接式的 `"Strap-On Temperature Sensor | 3K Thermistor | Resistance Output | ..."`，长度和风格都不是"产品名"。
- 对 Layer 3 语义匹配没有致命影响（Short_Description 足够），但如果前端要展示"最接近的产品是 X"，直接显示 Short_Description 用户体验不好。

**建议跟 eParts 确认：** Product_Name 是被刻意留空（业务上不维护这个字段），还是导出时漏掉了？

### 4.3 ⚠️ P1-A 的"输入"不是真正的客户原文

readme 明确写：
> The description columns are what our product team wrote after reviewing spec sheets — treat these as the "input text."

换句话说，1A 里的 Short/Full/Extended_Description 是 **eParts 内部产品团队整理后的规范描述**，不是客户真正发来的邮件 / PDF 摘要 / 表单内容。

**这对我们的系统意味着什么：**
- ✅ 对 Layer 3 语义匹配 **够用**：模型学到的是"产品描述 → 属性"的映射关系，这个映射不因输入来源改变。
- ❌ 对 Layer 1 文本提取、Layer 2 规则引擎 **不够**：
  - 真实邮件会有问候语、签名、错别字、单位写法不一致（"24VAC" vs "24 V AC" vs "24 vac"）、省略重要信息、夹带无关信息。
  - 整理后的描述是"干净版本"，模型在这上面训出来的规则和阈值，上线后会遇到分布漂移。
- ❌ 对置信度校准 **不够**：干净数据上训的 σ（高斯衰减参数）会偏乐观，上线后所有输入都会被打出过高的置信度。

**建议：**
- 短期：用 1A 训练语义匹配层的"参考区域"。
- 中期：从 1A_Product_Document_Links 的 PDF OCR 出文本，作为**噪声更接近真实输入的训练集**，重新校准 σ。
- 长期：**必须向 eParts 索取真实客户原始输入**（邮件正文片段、PDF 抽取结果、工单文本），至少 50-100 条用于最终校准和上线前验收。

### 4.4 ⚠️ 属性覆盖度有缺口

- Data Dictionary 写 **487 个 active 属性**。
- 1A 实际出现 348 个，2A 出现 346 个。
- **约 29% 的 active 属性在交付的数据里没有任何实际样例。**

**影响：** 如果客户请求正好落在这 141 个"无数据"的属性上，模型没有任何训练信号，只能兜底到规则匹配或完全不确定。

**建议：** 让 eParts 给出"未出现属性"的名单，确认它们是：
- (a) 新增的、尚无产品使用 → 可以忽略
- (b) 因某些字段过滤条件被排除 → 需要重新拉取
- (c) 极罕见的长尾属性 → 在模型侧做特判

### 4.5 ⚠️ 长尾属性样本不足

即使在 348 个有数据的属性里，也有一批**样本数 ≤ 5** 的属性（如 `HOLDING FORCE`、`LATCH TYPE`、`APERTURE SIZE [W x H]` 各只有 1-3 条）。

**对比 Proposal 里的 PAC 下界**：
- 理论最小 4-5 样本/属性
- 工程推荐 20-50 样本/属性

这批长尾属性**低于工程推荐值**，模型在这些属性上的泛化能力会弱。

### 4.6 ❌ P3-A 客户提交模板 / P3-B 请求量分布 —— 完全未交付

P3 是加分项不阻塞建模，但缺失意味着：
- 规则引擎没法针对主流模板（Excel 订单表、HVAC 承包商表单）写专项解析。
- 训练数据投入无法按请求频率加权，模型可能在低频品类上过拟合，在高频品类上欠拟合。

---

## 五、建议的后续动作

按优先级排序：

### P0 — 必须跟 eParts 澄清
1. **2B 错误案例重新交付**。需要 50+ 条**真正的语义修正**：明确"初版属性值/品类 → 修正后"。形式最好是人工挑选的 case，不是从 Edit Log 全量导出。
2. **真实客户输入样例**。哪怕 30-50 条匿名化的邮件 / PDF 抽取文本，用于最终校准。
3. **Product_Name 字段是否可补？** 确认是刻意留空还是导出疏漏。

### P1 — 我们自己可以先做
1. **用 1A 建 baseline 模型**。数据量完全够，可以先走完四层 pipeline 端到端。
2. **从 1A-Links 的 PDF OCR 生成合成测试集**。在没有真实客户文本前，这是次优方案。
3. **按 ProductType 分层训练**。19.8 万产品分布在 382 个 ProductType，平均 520 个/类，完全可以每类单独训一个参考区域。
4. **属性长尾清单**。标记出样本数 < 20 的属性，在置信度输出时对这些属性天然打压上限（如 conf_final ≤ 0.7）。

### P2 — 锦上添花
1. 请 eParts 补 P3-A（客户模板）和 P3-B（请求分布）。
2. 做一份数据质量监控报表，上线后持续跟踪属性覆盖、OOV 词汇、置信度分布漂移。

---

## 六、附录：关键数据摘要

```
文件                                  行数         唯一产品    唯一属性   主要问题
1A_Product_Attribute_Pairs.csv      1,938,426    134,117    348        输入非客户原文
1A_Product_Document_Links.csv         516,005    178,194    —          超额交付
1B_Product_Master.csv                 198,147    198,147    —          Product_Name 近全空
2A_Values_Per_Attribute.csv             9,918    —          346        4.8% 空值行
2B_Apparent_Correction_Cases.csv      746,845     25,203    —          非真实错误案例
```

---

*评估人：MSE Studio Team — 2026-04-16*
