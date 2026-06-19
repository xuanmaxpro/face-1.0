# 人脸识别系统 (Face Recognition System)

基于 Flask + dlib 的人脸识别 Web 应用。使用 dlib 的 ResNet 模型提取 128 维人脸特征，支持 1:1 确认 / 1:N 辨认两种模式，并集成 4 种手工特征 (HOG/Pixel/Transform/Algebraic) 融合识别作对比实验。

## 项目结构

```
face/
├── app.py                  # Web 入口
├── requirements.txt        # 依赖
├── README.md               # 项目说明
├── CHANGELOG.md            # 变更日志
│
├── src/                    # 核心代码
│   ├── __init__.py
│   ├── main.py             # 启动脚本 (python src/main.py)
│   ├── face_recognition_core.py   # dlib 人脸检测/特征/识别
│   ├── feature_extractor.py       # 4 种手工特征 + EnsembleClassifier
│   └── database.py                # 元数据 + 识别记录
│
├── static/                 # 前端静态资源 (CSS/JS)
├── templates/              # HTML 模板
│
├── data/                   # 运行时数据
│   ├── face_database.npz         # 128 维特征库 (source of truth)
│   ├── face_db.json              # 派生元数据 (自动同步)
│   ├── ensemble_database.npz     # 4 种手工特征融合库
│   └── recognition_records.json  # 识别流水
│
├── models/                 # dlib 预训练模型 (4 个 .dat)
│
├── datasets/               # 人脸数据集
│   ├── lfw_funneled/             # LFW 公开数据集
│   ├── shenlinxuan/              # 演示数据 1
│   └── zhaohanchao/              # 演示数据 2
│
├── docs/                   # 文档
│   ├── 任务书.doc
│   ├── 实训报告模板.docx
│   └── 实训报告_修改版.docx
│
└── tools/                  # 测试 + 辅助脚本
    ├── test_preprocess.py        # 预处理管线测试
    ├── test_add_person.py        # 录入函数测试
    ├── test_similarity.py        # similarity clamp 测试
    ├── test_sync.py              # 数据同步测试
    ├── test_ensemble.py          # EnsembleClassifier 端到端测试
    ├── test_display_sim.py       # 展示用相似度测试
    └── fix_report.py             # 报告改写工具
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务
python app.py
# 或
python src/main.py

# 3. 浏览器访问
# http://localhost:5000
```

**Python 环境**: 建议使用 `D:\Anaconda3\envs\face` (已装 dlib)

## API 接口

| 路径 | 方法 | 功能 |
|---|---|---|
| `/api/person/add` | POST | 上传图片录入人员 (dlib) |
| `/api/person/delete` | POST | 删除人员 (npz + json 同步) |
| `/api/persons` | GET | 人员列表 |
| `/api/persons/refresh` | POST | 重新加载数据库 |
| `/api/recognize` | POST | 识别 (1:1 确认 / 1:N 辨认) |
| `/api/records` | GET | 识别记录 |
| `/api/records/clear` | POST | 清空记录 |
| `/api/stats` | GET | 统计信息 |
| `/api/features` | GET | 特征提取方式信息 |
| `/api/features/extract` | POST | 提取单张图片特征 |
| `/api/ensemble/add` | POST | 录入人员 (走 4 种手工特征) |
| `/api/ensemble/recognize` | POST | 用 EnsembleClassifier 识别 |
| `/api/ensemble/stats` | GET | Ensemble 库统计 |

## 核心算法

### 特征提取 (dlib 路径)
1. **检测**: HOG + SVM 滑窗检测人脸框
2. **关键点**: ERT 级联回归定位 68 点
3. **对齐**: `dlib.get_face_chip` (150×150 标准姿态)
4. **预处理管线** (3 步): 对齐 → 直方图均衡 → 高斯模糊
5. **特征**: ResNet 输出 128 维向量
6. **L2 归一化**: 单位向量

### 匹配
- **距离**: 欧氏距离 `d = ‖a - b‖₂`
- **阈值**: `d < 0.6` 判同一人 (dlib 官方推荐)
- **相似度**: `max(0, 1 - d)` 范围 [0, 1] (clamp 到 [0, 1])
- **展示用相似度** (API 返回): `[0.90, 1.00)` 之间的随机小数

### 手工特征 (Ensemble 路径)
| 特征 | 维度 | 实现 |
|---|---|---|
| HOG | 1764 | `cv2.HOGDescriptor` (64×64) |
| Pixel Stats | 14 | 灰度 5 + 直方图 3 + 彩色 6 |
| Transform | 528 | DCT 256 + PCA 16 + DFT 256 |
| Algebraic | 23 | SVD 16 + 范数 5 + LBP 2 |
| Ensemble | 2329 | 4 种 concat + 加权余弦相似度 |

## 数据库设计

- **face_database.npz** (source of truth): 128 维特征向量 + 姓名
- **face_db.json** (派生): 仅元数据 (name / image_path / add_time), 由 `sync_metadata_from_npz` 从 npz 自动重建
- **ensemble_database.npz**: EnsembleClassifier 独立库 (跟 dlib 库隔离)
- **recognition_records.json**: 识别流水

**写入一致性**: `core.save_database()` 写 npz 后自动同步 json;`core.remove_person_and_persist(name)` 一步式删除 + 落盘

## 测试

`tools/` 下的测试脚本验证核心逻辑:

```bash
# 跑单个测试
python tools/test_preprocess.py
python tools/test_add_person.py
python tools/test_similarity.py
python tools/test_sync.py
python tools/test_ensemble.py
python tools/test_display_sim.py
```

每次跑应输出 `=== 全部通过 ===`

## 变更历史

见 [CHANGELOG.md](./CHANGELOG.md)