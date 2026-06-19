// ==================== 特征数据 ====================
const FEATURES = [
    {
        id: 'resnet',
        name: 'ResNet',
        dimension: 128,
        category: '深度学习',
        color: '#3b82f6',
        icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="20" rx="3"/><path d="M7 12h2l2-4 2 8 2-4h2"/></svg>`,
        summary: '基于深度残差网络的人脸特征提取，输出 128 维嵌入向量',
        principle: `ResNet（残差网络）特征提取利用预训练的深度卷积神经网络，将人脸图像映射到一个 128 维的紧凑嵌入空间中。

核心原理：
1. **残差学习**：通过跳跃连接（Skip Connection）解决深层网络的梯度消失问题，使网络可以学习残差映射 F(x) = H(x) - x，而非直接学习 H(x)
2. **人脸对齐**：使用 dlib 的 68 点人脸关键点检测器定位人脸，通过仿射变换将人脸对齐到标准姿态
3. **嵌入提取**：将 150×150 的对齐人脸输入 ResNet，取最后一层全连接层的输出作为 128 维特征向量
4. **距离度量**：两张人脸的相似度通过特征向量的欧氏距离计算，距离越小越相似

本系统使用 dlib 预训练的 ResNet 模型，该模型在 LFW（Labeled Faces in the Wild）数据集上达到了 99.38% 的准确率。`,
        pros: [
            '识别精度极高，在标准数据集上准确率超过 99%',
            '对人脸姿态、光照、表情变化有很强的鲁棒性',
            '特征维度低（128d），存储和匹配效率高',
            '预训练模型开箱即用，无需额外训练数据',
            '对部分遮挡（如戴眼镜、口罩）有一定容忍度'
        ],
        cons: [
            '依赖 dlib 库和预训练模型，模型文件较大（约 100MB）',
            '特征提取速度相对较慢，需要 GPU 加速才能达到实时',
            '模型不可解释，无法直观理解特征含义',
            '对极端姿态（侧脸 > 45°）识别率显著下降',
            '需要人脸对齐预处理，对齐失败会影响识别效果'
        ],
        suitable: '大规模人脸识别系统、实时门禁考勤、安防监控、金融级身份认证等对精度要求极高的场景',
        notSuitable: '嵌入式设备、无 GPU 的轻量级部署、需要特征可解释性的学术研究'
    },
    {
        id: 'hog',
        name: 'HOG',
        dimension: 1764,
        category: '传统视觉',
        color: '#f59e0b',
        icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>`,
        summary: '方向梯度直方图，统计局部区域的梯度方向分布特征',
        principle: `HOG（Histogram of Oriented Gradients）是一种经典的局部特征描述子，通过统计图像局部区域的梯度方向分布来描述物体形状。

核心原理：
1. **梯度计算**：对图像每个像素计算水平方向 Gx 和垂直方向 Gy 的梯度，得到梯度幅值 |G| = √(Gx² + Gy²) 和方向 θ = arctan(Gy/Gx)
2. **单元格划分**：将图像划分为 8×8 像素的单元格（Cell）
3. **方向直方图**：在每个单元格内，将 0°-180° 的梯度方向量化为 9 个 bin，根据梯度幅值加权投票
4. **块归一化**：将 2×2 个单元格组成一个块（Block），对块内的 36 维向量进行 L2-Hys 归一化，消除光照影响
5. **特征拼接**：将所有块的归一化直方图拼接成最终特征向量

对于 64×64 的人脸图像，使用 8×8 Cell 和 2×2 Block，最终得到 7×7×2×2×9 = 1764 维特征。`,
        pros: [
            '计算速度快，无需 GPU 即可实时处理',
            '对光照变化有一定鲁棒性（归一化处理）',
            '算法原理清晰，特征可解释性强',
            '不依赖外部模型文件，部署轻量',
            '适合资源受限的嵌入式场景'
        ],
        cons: [
            '特征维度高（1764d），存储和匹配开销大',
            '对旋转和姿态变化敏感，正脸识别效果远好于侧脸',
            '对表情变化和年龄变化的鲁棒性不足',
            '识别精度远低于深度学习方法',
            '梯度信息在高频噪声下不稳定'
        ],
        suitable: '资源受限的嵌入式设备、正脸识别的简单门禁、教学演示、对实时性要求高但精度要求一般的场景',
        notSuitable: '大姿态变化场景、安防级别应用、需要高精度的身份认证'
    },
    {
        id: 'pixel',
        name: 'Pixel Stats',
        dimension: 20,
        category: '统计特征',
        color: '#22c55e',
        icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
        summary: '像素统计特征，提取灰度分布和颜色通道的统计量',
        principle: `Pixel Stats（像素统计特征）通过计算人脸图像的灰度分布和颜色通道统计量来描述人脸的整体外观特征。

核心原理：
1. **灰度统计（5维）**：计算灰度图的均值、标准差、偏度、峰度和熵
   - 均值：反映整体亮度
   - 标准差：反映对比度
   - 偏度：反映亮度分布的对称性
   - 峰度：反映亮度分布的尖锐程度
   - 熵：反映信息量

2. **直方图特征（3维）**：将灰度直方图分为低、中、高三个区间，统计各区间的像素比例

3. **颜色统计（12维）**：在 RGB 和 HSV 两个颜色空间中，分别计算各通道的均值和标准差
   - RGB 空间：R/G/B 各通道均值 + 标准差 = 6 维
   - HSV 空间：H/S/V 各通道均值 + 标准差 = 6 维

最终拼接得到 5 + 3 + 12 = 20 维特征向量。`,
        pros: [
            '特征维度极低（20d），存储和计算开销极小',
            '计算速度极快，适合大规模初筛',
            '包含颜色信息，对肤色特征有一定区分力',
            '实现简单，无需复杂算法和模型',
            '可作为集成学习的有效补充特征'
        ],
        cons: [
            '区分能力非常有限，单独使用几乎无法识别',
            '对光照变化极为敏感，同一人不同光照下特征差异大',
            '丢失了空间结构信息，无法区分五官位置',
            '对表情、姿态、年龄变化无鲁棒性',
            '不同人种/肤色的区分可能引入偏差'
        ],
        suitable: '大规模人脸库的粗筛预过滤、集成学习中的辅助特征、资源极度受限的设备、快速人脸检测的辅助判断',
        notSuitable: '任何需要精确识别的场景、独立使用的人脸认证系统'
    },
    {
        id: 'transform',
        name: 'Transform',
        dimension: 304,
        category: '频域特征',
        color: '#a855f7',
        icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 12c2-4 4-8 6-4s4 8 6 4 4-8 6-4"/><path d="M2 17c2-4 4-8 6-4s4 8 6 4 4-8 6-4"/></svg>`,
        summary: '变换域特征，利用 DCT/DFT 频域变换和 PCA 降维提取特征',
        principle: `Transform（变换域特征）利用频域变换将人脸图像从空间域转换到频率域，提取频域系数作为特征。

核心原理：
1. **DCT 离散余弦变换（256维）**：
   - 将人脸图像进行 2D-DCT 变换，得到频域系数矩阵
   - 低频系数对应人脸整体轮廓，高频系数对应细节纹理
   - 保留左上角 16×16 = 256 个低频系数，丢弃高频噪声
   - DCT 具有能量集中特性，主要信息集中在少数低频系数中

2. **PCA 主成分分析（16维）**：
   - 对 DCT 系数进行 PCA 降维
   - 保留前 16 个主成分，捕获最大方差方向
   - PCA 通过特征值分解找到数据的最优低维表示

3. **DFT 离散傅里叶变换（32维）**：
   - 对人脸图像进行 2D-DFT 变换
   - 取频谱幅值的低频部分 32 个系数
   - DFT 的相位信息对人脸对齐敏感，因此只使用幅值

最终拼接得到 256 + 16 + 32 = 304 维特征向量。`,
        pros: [
            '频域特征对空间域的平移有一定不变性',
            'DCT 能量集中，少量系数即可保留主要信息',
            'PCA 降维有效去除冗余，提高判别力',
            '频域分析可揭示空间域不易观察的周期性特征',
            '对适度的高斯噪声有滤波效果'
        ],
        cons: [
            '对图像对齐精度要求高，偏移会导致频谱变化',
            'DFT 的相位信息丢失，损失了部分空间结构',
            'PCA 需要训练数据来计算主成分，泛化能力受限',
            '频域特征可解释性较差，难以直观理解',
            '单独使用识别精度有限，不如深度学习方法'
        ],
        suitable: '频域分析研究、与空间域特征互补融合、对噪声有要求的场景、学术研究中的人脸频域特性探索',
        notSuitable: '独立用于高精度识别、实时性要求极高的场景（DCT/DFT 计算开销较大）'
    },
    {
        id: 'algebraic',
        name: 'Algebraic',
        dimension: 50,
        category: '代数特征',
        color: '#ec4899',
        icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>`,
        summary: '代数特征，利用 SVD 分解、矩阵范数和 LBP 提取结构化特征',
        principle: `Algebraic（代数特征）利用矩阵代数运算从人脸图像中提取结构化的数学特征。

核心原理：
1. **SVD 奇异值分解（16维）**：
   - 将人脸灰度图视为矩阵 A，进行 SVD 分解：A = UΣV^T
   - 奇异值 σ₁ ≥ σ₂ ≥ ... ≥ σᵣ 反映矩阵的"能量分布"
   - 保留前 16 个最大奇异值作为特征
   - 奇异值具有旋转不变性、平移不变性等优良性质
   - 奇异值的大小反映图像中对应成分的重要程度

2. **矩阵范数（5维）**：
   - 计算图像矩阵的多种范数作为全局特征
   - L1 范数（绝对值之和）：反映整体能量
   - L2 范数（Frobenius 范数）：反映信号强度
   - L∞ 范数（最大绝对值）：反映峰值
   - 核范数（奇异值之和）：反映矩阵秩的近似
   - L2,1 范数：行稀疏性度量

3. **LBP 局部二值模式（29维）**：
   - 对每个像素，与其 8 邻域比较大小，生成 8 位二进制码
   - 统计统一模式（Uniform Pattern，0→1 或 1→0 跳变 ≤ 2 次）的直方图
   - 统一模式共 58 种，合并非统一模式得到 59 bin 直方图
   - 本系统取前 29 个最高频 bin 作为特征

最终拼接得到 16 + 5 + 29 = 50 维特征向量。`,
        pros: [
            'SVD 奇异值具有优良的数学性质（旋转/平移不变性）',
            '特征维度适中（50d），计算和存储效率高',
            'LBP 对单调灰度变化具有不变性，适合光照变化场景',
            '矩阵范数提供全局结构信息，计算简单',
            '数学基础扎实，特征含义清晰可解释'
        ],
        cons: [
            'SVD 分解计算量较大，对大图像效率不高',
            '奇异值丢失了空间位置信息，不同结构可能产生相似奇异值',
            'LBP 对非单调光照变化（如侧光）鲁棒性不足',
            '单独使用识别精度较低，难以区分相似人脸',
            '范数特征过于粗粒度，区分能力有限'
        ],
        suitable: '学术研究中的人脸代数特性分析、光照相对稳定的受控环境、集成学习中的互补特征、需要特征可解释性的场景',
        notSuitable: '复杂光照环境、大姿态变化场景、独立用于高精度识别'
    },
    {
        id: 'ensemble',
        name: 'Ensemble',
        dimension: 2138,
        category: '融合特征',
        color: '#06b6d4',
        icon: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="4" r="2"/><circle cx="20" cy="12" r="2"/><circle cx="12" cy="20" r="2"/><circle cx="4" cy="12" r="2"/><line x1="12" y1="7" x2="12" y2="9"/><line x1="17" y1="12" x2="15" y2="12"/><line x1="12" y1="17" x2="12" y2="15"/><line x1="7" y1="12" x2="9" y2="12"/></svg>`,
        summary: '融合四种手工特征的多维度特征表示，兼顾全局与局部信息',
        principle: `Ensemble（融合特征）将 HOG、Pixel Stats、Transform、Algebraic 四种手工特征拼接融合，形成多维度的综合特征表示。

核心原理：
1. **特征拼接**：将四种互补特征直接拼接
   - HOG（1764d）：局部梯度方向信息 → 捕获边缘和形状
   - Pixel Stats（20d）：全局统计信息 → 捕获亮度和颜色分布
   - Transform（304d）：频域信息 → 捕获频率分布特性
   - Algebraic（50d）：结构信息 → 捕获矩阵代数性质
   - 总维度：1764 + 20 + 304 + 50 = 2138d

2. **加权融合**：在识别阶段，对四种特征分别计算相似度，再按权重加权融合
   - 权重分配基于各特征在验证集上的区分能力
   - 默认权重：HOG 0.40, Pixel 0.10, Transform 0.30, Algebraic 0.20
   - HOG 权重最高，因为梯度方向信息对人脸区分贡献最大

3. **决策融合**：最终识别结果由加权相似度综合决定
   - 综合相似度 = w₁·sim_hog + w₂·sim_pixel + w₃·sim_transform + w₄·sim_algebraic
   - 综合相似度超过阈值则判定为同一人

这种融合策略的核心理念是：不同特征从不同角度描述人脸，互补性可以弥补单一特征的不足。`,
        pros: [
            '多维度特征互补，综合识别精度高于任何单一手工特征',
            '同时包含局部（HOG）和全局（Pixel/Algebraic）信息',
            '同时包含空间域（HOG/LBP）和频率域（DCT/DFT）信息',
            '加权融合策略灵活，可根据场景调整权重',
            '可用于对比验证深度学习 vs 传统方法的性能差异'
        ],
        cons: [
            '特征维度极高（2138d），存储开销大',
            '匹配计算量大，不适合大规模人脸库的实时检索',
            '四种特征直接拼接存在信息冗余',
            '权重需要手动调优或交叉验证确定',
            '即使融合，精度仍远低于 ResNet 深度学习特征'
        ],
        suitable: '学术研究中传统方法与深度学习的对比实验、中小规模人脸库的高精度识别、答辩演示中展示特征融合效果、需要多角度特征分析的场景',
        notSuitable: '大规模人脸库（>1000人）的实时检索、存储资源受限的嵌入式部署、对精度有极致要求的安防应用'
    }
];

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    renderFeatureCards();
});

// ==================== 渲染卡片 ====================
function renderFeatureCards() {
    const grid = document.getElementById('featuresGrid');
    let html = '';

    FEATURES.forEach(f => {
        html += `
            <div class="feature-intro-card" onclick="openDetail('${f.id}')" style="--card-accent: ${f.color}">
                <div class="feature-card-icon">${f.icon}</div>
                <div class="feature-card-body">
                    <div class="feature-card-name">${f.name}</div>
                    <div class="feature-card-dim">${f.dimension}d</div>
                    <div class="feature-card-category">${f.category}</div>
                </div>
                <p class="feature-card-summary">${f.summary}</p>
                <div class="feature-card-action">
                    <span>查看详情</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </div>
            </div>
        `;
    });

    grid.innerHTML = html;
}

// ==================== 详情弹窗 ====================
function openDetail(id) {
    const f = FEATURES.find(item => item.id === id);
    if (!f) return;

    document.getElementById('detailIcon').innerHTML = f.icon;
    document.getElementById('detailIcon').style.color = f.color;
    document.getElementById('detailName').textContent = f.name;
    document.getElementById('detailDim').textContent = `${f.dimension} 维 · ${f.category}`;

    let bodyHtml = '';

    // 原理
    bodyHtml += `
        <div class="detail-section">
            <h4 class="detail-section-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${f.color}" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                原理
            </h4>
            <div class="detail-principle">${f.principle.replace(/\n/g, '<br>')}</div>
        </div>
    `;

    // 优缺点
    bodyHtml += `
        <div class="detail-section">
            <div class="detail-pros-cons">
                <div class="detail-pros">
                    <h4 class="detail-section-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                        优点
                    </h4>
                    <ul class="detail-list">
                        ${f.pros.map(p => `<li>${p}</li>`).join('')}
                    </ul>
                </div>
                <div class="detail-cons">
                    <h4 class="detail-section-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                        缺点
                    </h4>
                    <ul class="detail-list">
                        ${f.cons.map(c => `<li>${c}</li>`).join('')}
                    </ul>
                </div>
            </div>
        </div>
    `;

    // 适用场景
    bodyHtml += `
        <div class="detail-section">
            <div class="detail-scenarios">
                <div class="scenario-card scenario-suitable">
                    <h4 class="detail-section-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                        适用场景
                    </h4>
                    <p>${f.suitable}</p>
                </div>
                <div class="scenario-card scenario-not-suitable">
                    <h4 class="detail-section-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                        不适用场景
                    </h4>
                    <p>${f.notSuitable}</p>
                </div>
            </div>
        </div>
    `;

    document.getElementById('detailBody').innerHTML = bodyHtml;
    document.getElementById('featureDetailModal').hidden = false;
}

function closeDetail() {
    document.getElementById('featureDetailModal').hidden = true;
}

// ESC 关闭弹窗
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDetail();
});
