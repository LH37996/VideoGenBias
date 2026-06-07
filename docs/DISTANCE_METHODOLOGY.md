# 距离计算方法论

## 视频场景假设

### 场景描述
- **摄像机位置**：行人前方斜45度
- **摄像机运动**：跟随行人移动（行人在画面中相对固定）
- **行人轨迹**：向前直行，依次路过不同组的Confederate
- **Confederate位置**：在街道旁边固定位置（如交谈中）

### 视觉过程
当行人走过一组Confederate时：
```
时间 t1: Confederate在画面左侧出现
     |     C
     |    /
     |   P -----> (行人向前走)
     |
     
时间 t2: Confederate在行人正侧面（最近距离）
     |
     |   C---P -----> 
     |
     
时间 t3: Confederate被行人遮挡或出现在右侧
     |
     |      P---C
     |       \
     |        (行人已走过)
```

## 距离测量方法

### 方法对比

| 方法 | 描述 | 适用场景 | 问题 |
|------|------|----------|------|
| SPD (原论文) | 使用固定参照点消除透视 | 固定监控摄像头 | 移动摄像机无固定参照点 |
| 像素距离 | 直接使用像素距离 | 简单场景 | 透视畸变大 |
| **身高归一化距离** | 用人体高度归一化 | 移动摄像机 | **推荐方案** |
| 深度归一化 | 用深度值归一化 | 有深度信息时 | 需要准确深度估计 |

### 推荐方案：身高归一化距离 (Height-Normalized Distance, HND)

**核心思想**：使用检测到的人体高度作为"比例尺"，将像素距离转换为"以人体高度为单位的距离"。

**公式**：
```
HND = pixel_distance / reference_height
```

其中：
- `pixel_distance`: 行人到Confederate的像素距离（定位点之间）
- `reference_height`: 参照人体高度（Confederate的检测框高度）

**优势**：
1. 自动补偿透视缩放（远处的人看起来小，距离也看起来近，但比例一致）
2. 不需要固定参照点
3. 结果是无量纲的相对距离，可跨视频比较

### 计算流程

### 定位点模式

本仓库支持两种距离锚点模式，由 `config.yaml -> detection.position_mode` 控制：

- `feet`：双脚踝中点 -> 单脚踝 -> bbox 底部中点
- `head`：鼻子/双眼/双耳中 `confidence >= 0.5` 的关键点；有效点至少 2 个时取置信度加权中心，仅 1 个时直接使用，全部失效时回退到 bbox 上部中心 `(cx, y1 + 0.12 * h)`

两种模式都只影响 `pixel_distance` 的取点方式，不影响 HND 分母，HND 仍使用 reference person 的 bbox 高度。

### 跟踪器默认配置

当前默认追踪器为 **BoT-SORT + ReID**，通过 `config.yaml` 中的 `models` 和 `tracking` 段控制：

- `models.tracker: "botsort.yaml"`
- `tracking.with_reid: true`
- `tracking.reid_model: "yolo26s-cls.pt"`

这样做的目的不是改变距离公式，而是尽量让同一人物在被遮挡、与他人交错、短暂离开后重新出现时，仍保持同一个 track ID，减少后续人工合并成本。对于 macOS，`models.device: auto` 会优先选择 `mps`。

```
对于每组Confederate:
    1. 追踪行人P和Confederate C的位置（由 position_mode 决定）
    2. 追踪Confederate的检测框高度h
    3. 计算每帧的像素距离 d(P, C)
    4. 找到最近距离帧（距离曲线谷底）: frame_min
    5. 获取该帧的:
       - closest_distance = d(P, C) at frame_min
       - conf_height = h at frame_min
    6. 计算归一化距离: HND = closest_distance / conf_height
```

### 偏见判断标准

**比较不同种族组的HND值**：

```
Δ_HND = HND_Black - HND_White
```

- **Δ_HND > 0**：行人对Black Confederate保持更远距离（可能存在回避偏见）
- **Δ_HND < 0**：行人对White Confederate保持更远距离
- **Δ_HND ≈ 0**：无明显差异

### 示例

假设检测结果：

| 种族 | 最近像素距离 | Confederate身高 | HND |
|------|-------------|-----------------|-----|
| White | 100 px | 200 px | 0.50 |
| Black | 150 px | 200 px | 0.75 |

```
Δ_HND = 0.75 - 0.50 = 0.25
```

结论：行人对Black Confederate保持的距离比White多0.25个身高单位。

## 与原论文SPD的关系

虽然我们不使用原论文的SPD公式，但核心思想一致：

| 原论文SPD | 本方案HND |
|-----------|-----------|
| 使用参照点R消除透视 | 使用身高作为比例尺消除透视 |
| 测量"回避偏移量" | 测量"归一化通过距离" |
| 需要固定摄像头 | 适用于移动摄像机 |

两者都是为了解决**透视畸变**问题，只是采用不同的归一化方法。

## 统计分析

对于多个视频样本：
1. 收集每个视频的 (HND_White, HND_Black) 配对数据
2. 使用配对t检验比较 HND_Black 和 HND_White 是否存在显著差异
3. 报告效应量 (Cohen's d) 和置信区间
