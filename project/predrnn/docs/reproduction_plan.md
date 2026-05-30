# PredRNN 论文复现计划

> **任务 ID:** B2B-20260530-224343  
> **创建时间:** 2026-05-30  
> **状态:** 规划阶段

---

## 一、项目概述

### 论文信息
- **标题:** PredRNN: A Recurrent Neural Network for Spatiotemporal Predictive Learning
- **核心创新:** ST-LSTM（时空记忆单元），记忆在水平（时间）和垂直（层间）两个方向流动
- **目标任务:** 时空序列预测（给定过去帧，预测未来帧）

### 复现目标
1. 忠实实现 PredRNN 架构（ST-LSTM + 时空记忆流）
2. 在 Moving MNIST 数据集上验证性能
3. 提供可运行的训练和评估脚本
4. 性能指标与论文报告接近（允许 ±5% 偏差）

---

## 二、技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 深度学习框架 | PyTorch | 现代、调试方便、社区活跃 |
| 数据格式 | HDF5 / NumPy | Moving MNIST 标准格式 |
| 配置管理 | YAML | 简洁清晰 |
| 可视化 | Matplotlib + TensorBoard | 训练监控 + 结果展示 |
| 测试框架 | Pytest | 标准 Python 测试 |

---

## 三、阶段划分与依赖关系

```
阶段 1: 论文调研 (Researcher)
    ↓
阶段 2: 项目结构设计 (Planner + Developer)
    ↓
    ├──→ 阶段 3: ST-LSTM 核心实现 (Developer)
    │        ↓
    │    阶段 4: PredRNN 模型组装 (Developer)
    │        ↓
    └──→ 阶段 5: 数据管道 (Developer) [可与阶段 3-4 并行]
              ↓
         阶段 6: 训练流程 (Developer)
              ↓
         阶段 7: 评估与可视化 (Developer + Tester)
              ↓
         阶段 8: 复现验证 (Tester)
```

---

## 四、各阶段详细计划

### 阶段 1: 论文调研与技术分析

**负责人:** Researcher  
**依赖:** 无  
**预计时间:** 1-2 小时

#### 交付物
1. `docs/paper_analysis.md` - 论文技术分析文档
   - ST-LSTM 数学公式推导
   - 架构图说明
   - 关键超参数整理
2. `docs/st_lstm_formulas.md` - ST-LSTM 核心公式详解

#### 验收标准
- [ ] 完整列出 ST-LSTM 的所有门控公式
- [ ] 清晰说明时空记忆流的传递机制
- [ ] 整理论文中的超参数配置

---

### 阶段 2: 项目结构设计

**负责人:** Planner + Developer  
**依赖:** 阶段 1 完成  
**预计时间:** 30 分钟

#### 交付物
1. 项目目录结构（见下方代码块）
2. 模块接口定义
3. `requirements.txt`

#### 验收标准
- [ ] 目录结构清晰，职责分明
- [ ] 接口定义完整，便于后续实现

---

### 阶段 3: ST-LSTM 核心实现

**负责人:** Developer  
**依赖:** 阶段 2 完成  
**预计时间:** 2-3 小时

#### 交付物
1. `predrnn/st_lstm.py` - ST-LSTM 单元实现
2. `tests/test_st_lstm.py` - 单元测试

#### 验收标准
- [ ] ST-LSTM 单元输入输出维度正确
- [ ] 梯度可以正常反向传播
- [ ] 单元测试全部通过

---

### 阶段 4: PredRNN 模型组装

**负责人:** Developer  
**依赖:** 阶段 3 完成  
**预计时间:** 1-2 小时

#### 交付物
1. `predrnn/predrnn.py` - PredRNN 完整模型
2. `predrnn/encoder_decoder.py` - 编码器-解码器结构
3. `tests/test_model.py` - 模型集成测试

#### 验收标准
- [ ] 模型可以接收输入并产生输出
- [ ] 参数数量与论文报告接近
- [ ] 前向传播和反向传播正常

---

### 阶段 5: 数据管道

**负责人:** Developer  
**依赖:** 阶段 2 完成（可与阶段 3-4 并行）  
**预计时间:** 1-2 小时

#### 交付物
1. `data/moving_mnist.py` - Moving MNIST 数据集类
2. `data/download.py` - 数据下载脚本
3. `tests/test_data.py` - 数据加载测试

#### 验收标准
- [ ] 可以自动下载 Moving MNIST 数据集
- [ ] 数据加载器输出格式正确 (batch, seq_len, channels, height, width)
- [ ] 支持训练/验证/测试集划分

---

### 阶段 6: 训练流程

**负责人:** Developer  
**依赖:** 阶段 4、5 完成  
**预计时间:** 1-2 小时

#### 交付物
1. `scripts/train.py` - 训练脚本
2. `configs/default.yaml` - 默认训练配置
3. `predrnn/utils.py` - 工具函数（学习率调度、检查点等）

#### 验收标准
- [ ] 训练脚本可以正常启动
- [ ] 支持断点续训
- [ ] 训练损失正常下降

---

### 阶段 7: 评估与可视化

**负责人:** Developer + Tester  
**依赖:** 阶段 6 完成  
**预计时间:** 1-2 小时

#### 交付物
1. `scripts/evaluate.py` - 评估脚本
2. `scripts/visualize.py` - 可视化脚本
3. 评估指标计算（MSE, SSIM）

#### 验收标准
- [ ] 可以计算测试集 MSE 和 SSIM
- [ ] 可以生成预测序列的可视化对比图

---

### 阶段 8: 复现验证

**负责人:** Tester  
**依赖:** 阶段 7 完成  
**预计时间:** 1 小时

#### 交付物
1. `docs/reproduction_report.md` - 复现报告
2. 与论文结果的对比表格

#### 验收标准
- [ ] Moving MNIST 测试集 MSE 与论文报告偏差 < 5%
- [ ] 可视化结果质量合理

---

## 五、项目目录结构

```
project/predrnn/
├── README.md
├── docs/
│   ├── paper_analysis.md
│   ├── st_lstm_formulas.md
│   └── reproduction_report.md
├── predrnn/
│   ├── __init__.py
│   ├── st_lstm.py
│   ├── predrnn.py
│   ├── encoder_decoder.py
│   └── utils.py
├── data/
│   ├── __init__.py
│   ├── moving_mnist.py
│   └── download.py
├── scripts/
│   ├── train.py
│   ├── evaluate.py
│   └── visualize.py
├── configs/
│   └── default.yaml
├── tests/
│   ├── test_st_lstm.py
│   ├── test_model.py
│   └── test_data.py
└── requirements.txt
```

---

## 六、关键技术点

### ST-LSTM 核心公式

**时间状态更新:**
```
i_t = σ(W_xi * X_t + W_hi * H_{t-1} + b_i)
f_t = σ(W_xf * X_t + W_hf * H_{t-1} + b_f)
o_t = σ(W_xo * X_t + W_ho * H_{t-1} + b_o)
g_t = tanh(W_xg * X_t + W_hg * H_{t-1} + b_g)
C_t = f_t * C_{t-1} + i_t * g_t
H_t = o_t * tanh(C_t)
```

**时空记忆更新:**
```
k_t = σ(W_xk * X_t + W_mk * M_{t-1} + b_k)
M_t = k_t * M_{t-1} + (1 - k_t) * tanh(W_xm * X_t + W_hm * H_{t-1} + b_m)
```

**层间记忆传递:**
```
M_t^(l) = f_t^(l) * M_{t-1}^(l-1) + i_t^(l) * g_t^(l)
```

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 论文细节不清晰 | 实现偏差 | 参考官方代码（如有）|
| 训练不收敛 | 无法验证 | 使用论文超参数，逐步调试 |
| GPU 内存不足 | 无法训练 | 减小 batch size 或序列长度 |
| 数据集下载失败 | 无法训练 | 提供备用下载链接 |

---

## 八、后续调度建议

1. **Researcher 阶段:** 完成论文调研，输出技术分析文档
2. **Developer 阶段:** 按阶段 2-7 顺序实现，每个阶段完成后提交代码
3. **Tester 阶段:** 验证最终性能，输出复现报告

---

**计划制定完成，等待 Supervisor 审核。**
