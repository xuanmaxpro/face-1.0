"""
Feature Extractor Module - 四种人脸特征提取方式
=================================================
本模块是"传统手工特征"的实现,用来跟 dlib ResNet 做对比实验。

四种特征:
    1. 视觉特征 (HOG)        —— 梯度方向直方图,1764 维
    2. 像素统计特征            —— 均值/标准差/直方图等,14 维
    3. 变换系数特征            —— DCT + PCA + DFT,共 528 维
    4. 代数特征 (SVD + LBP)    —— 奇异值/矩阵范数/LBP,共 23 维

把这些特征拼起来一共 2329 维,交给 EnsembleClassifier 加权融合识别。
注意:本模块不用于主识别流程(主流程是 face_recognition_core.py 用 dlib ResNet),
     只在 /api/ensemble/* 路由里被调用,做"传统方法 vs 深度学习"对比演示。
"""

import numpy as np
import cv2


class FeatureExtractor:
    """四种人脸特征提取器"""

    def __init__(self):
        # 初始化 HOG 描述符 (Histogram of Oriented Gradients)
        # 参数含义:
        #   (64, 64)  —— winSize, 检测窗口大小,所有输入图片都 resize 到这个尺寸
        #   (16, 16)  —— blockSize, 每 16x16 像素为一个 block (block 是 HOG 的统计单位)
        #   (8, 8)    —— blockStride, block 滑动的步长,跟 blockSize 一样意味着 block 之间不重叠
        #   (8, 8)    —— cellSize, 每个 cell 8x8 像素 (cell 是 block 的子单元)
        #   9         —— nbins, 梯度方向分成 9 桶 (0~180° 每 20° 一桶)
        # 注:OpenCV 默认 HOG 用 unsigned gradient (0~180°), 所以 9 桶够用
        self.hog = cv2.HOGDescriptor(
            (64, 64), (16, 16), (8, 8), (8, 8), 9
        )

    def extract_visual_features(self, gray_image):
        """
        1. 视觉特征 - HOG (Histogram of Oriented Gradients)
        通过计算图像局部区域的梯度方向直方图来描述人脸特征。

        思路:把图片切成很多 8x8 的小格子 (cell),每个 cell 统计
              "像素的边缘朝向哪个方向最多",形成 9 维直方图。
              4 个 cell 组成一个 16x16 的 block,块内 4 个直方图拼起来 + L2 归一化。
        输出:1764 维向量 (64x64 图,block 7x7=49 个,每个 block 36 维,49*36=1764)

        优点:对光照变化、平移比较鲁棒,在传统人脸识别里属于"老牌好用"。
        """
        # 把任意尺寸的灰度图缩放到 64x64,HOG 要求固定窗口大小
        resized = cv2.resize(gray_image, (64, 64))

        # 计算 HOG 特征,返回的是 1 列的列向量
        features = self.hog.compute(resized)
        # flatten() 把列向量压平成一维数组,方便后面 concatenate
        return features.flatten()

    def extract_pixel_statistics(self, image):
        """
        2. 像素统计特征 - 包括均值、标准差、最值、灰度直方图分布等
        思路:不关心像素位置,只看整张图的"亮暗分布、长什么样"。
        输出:14 维 (灰度5 + 直方图3 + 彩色6)
        """
        features = []  # 用 Python list 收集,最后转 numpy 数组

        # 如果输入是彩色图 (BGR, 3 维),先转灰度再做灰度统计
        # 如果已经是灰度图,直接用
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # ===== 5 个基本统计量 =====
        features.append(np.mean(gray))           # 均值:整张图平均亮度
        features.append(np.std(gray))            # 标准差:亮度起伏有多大
        features.append(np.min(gray))            # 最小值:最暗的像素
        features.append(np.max(gray))            # 最大值:最亮的像素
        features.append(np.median(gray))         # 中位数:比均值更抗极端值

        # ===== 灰度直方图 (256 桶) =====
        # calcHist([图], [通道], 掩膜, [分桶数], [值域]) —— 每个像素值落入哪一桶的计数
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        # 归一化:让所有桶加起来 = 1,这样下面的比例才有意义
        # +1e-10 防止全黑图除 0 (虽然不常见但要稳)
        hist = hist / (hist.sum() + 1e-10)

        # 从直方图再抽 3 个"概览型"特征
        features.append(np.sum(hist[:64]))       # 暗区比例:0~63 灰度的像素占比 (脸偏暗)
        features.append(np.sum(hist[128:]))      # 亮区比例:128~255 灰度的像素占比 (脸偏亮)
        features.append(np.argmax(hist))          # 峰值位置:出现最多的灰度值 (整张图的主调)

        # ===== 颜色直方图 (仅彩色图才有意义) =====
        # 如果原图是 BGR 3 通道,每个通道单独算 64 桶直方图,再取均值/标准差
        if len(image.shape) == 3:
            for i in range(3):  # i=0(B), i=1(G), i=2(R)
                h = cv2.calcHist([image], [i], None, [64], [0, 256]).flatten()
                features.append(np.mean(h))   # 这个通道的平均计数
                features.append(np.std(h))    # 这个通道的计数波动

        # 转 numpy 一维数组返回 (共 5+3+6=14 维)
        return np.array(features)

    def extract_transform_features(self, gray_image):
        """
        3. 变换系数特征 - 使用 DCT(离散余弦变换) + PCA(主成分分析) + DFT(离散傅里叶变换)
        思路:把图像从"空间域"变到"频率域",低频部分代表"大致长啥样",高频部分代表"边缘细节"。
        输出:528 维 (DCT 256 + PCA 16 + DFT 256)
        """
        features = []

        # 把图缩放到 64x64,并归一化到 [0,1] 浮点数
        # DCT/DFT 都要求浮点输入
        resized = cv2.resize(gray_image, (64, 64))
        img_float = np.float32(resized) / 255.0

        # ===== DCT (离散余弦变换) =====
        # JPEG 压缩用的就是这个。低频在左上角 (DCT 系数矩阵的左上),
        # 取 [0:16, 0:16] = 256 个低频系数,代表图像的"主体结构"。
        dct = cv2.dct(img_float)
        # 取低频部分作为特征
        dct_features = dct[:16, :16].flatten()
        features.extend(dct_features)

        # ===== PCA (主成分分析) =====
        # 算 64x64 灰度图的协方差矩阵 (描述像素两两之间的相关性)
        # 然后做特征值分解,特征值 = "该方向上的方差有多大"
        # 排序后取最大的 16 个,代表"图像变化最剧烈的 16 个方向"
        # 注:严格来说 PCA 应该把图片拉成一维向量再算协方差,这里实现略有不同,
        #     但效果上是类似的"找主要变化方向"
        cov = np.cov(resized)
        eigenvalues, eigenvectors = np.linalg.eig(cov)
        eigenvalues = np.sort(eigenvalues)[::-1]  # 降序
        pca_features = eigenvalues[:16].real      # 取前 16 个,取实部(特征值可能是复数)
        features.extend(pca_features)

        # ===== DFT (离散傅里叶变换) =====
        # DFT 把图像分解成不同频率的正弦/余弦波。
        # fftshift 把零频移到中心,中心区域就是低频信息。
        # log(|.|+1) —— 压缩动态范围,方便观察
        dft = np.fft.fft2(resized)
        dft_shift = np.fft.fftshift(dft)
        magnitude = np.log(np.abs(dft_shift) + 1)
        center_h, center_w = 32, 32  # 图中心 (64/2)
        h, w = 8, 8                  # 取中心 16x16 区域
        # 切出中心 16x16 = 256 个低频系数
        magnitude_center = magnitude[center_h-h:center_h+h, center_w-w:center_w+w].flatten()
        features.extend(magnitude_center)

        # 拼起来:256 + 16 + 256 = 528 维
        return np.array(features)

    def extract_algebraic_features(self, gray_image):
        """
        4. 代数特征 - 基于矩阵分解和代数操作 (SVD + 范数 + 迹 + LBP)
        思路:把图像看成一个矩阵,用线性代数的工具提取"几何/能量/纹理"信息。
        输出:23 维 (SVD 16 + 范数 4 + 迹 1 + LBP 2)
        """
        features = []

        # 缩放到 64x64,转浮点
        resized = cv2.resize(gray_image, (64, 64))
        img_float = np.float32(resized) / 255.0

        # ===== SVD (奇异值分解) =====
        # 把矩阵 A 分解成 U @ diag(s) @ V,其中 s 是奇异值,降序排列
        # 奇异值代表"图像在各个方向上的能量",前几个奇异值就能描述图像大部分信息
        u, s, v = np.linalg.svd(img_float)
        # 取前 16 个奇异值,除以最大值做归一化 (相对比例,跟图像整体亮度无关)
        svd_features = s[:16] / (s[0] + 1e-10)
        features.extend(svd_features)

        # ===== 矩阵范数 =====
        # 不同范数代表不同的"矩阵大小度量"
        features.append(np.linalg.norm(img_float, 'fro'))    # Frobenius 范数 = 所有元素平方和开根号
        features.append(np.linalg.norm(img_float, 'nuc'))    # 核范数 = 奇异值之和
        features.append(np.linalg.norm(img_float, 1))        # L1 范数 = 元素绝对值之和
        features.append(np.linalg.norm(img_float, 2))        # L2 范数 = 最大奇异值 (= SVD 的 s[0])

        # ===== 矩阵迹 =====
        # 迹 = A @ A.T 的对角线元素之和,代表"自相关总能量"
        features.append(np.trace(img_float @ img_float.T))

        # ===== LBP (局部二值模式) 统计 =====
        # LBP 是经典纹理描述子,这里只取均值和标准差作为 2 个特征
        lbp = self._compute_lbp(resized)
        features.append(np.mean(lbp))   # LBP 平均值
        features.append(np.std(lbp))    # LBP 标准差

        # 拼起来:16 + 4 + 1 + 2 = 23 维
        return np.array(features)

    def _compute_lbp(self, gray_image):
        """
        计算局部二值模式 (Local Binary Pattern)
        思路:对每个像素,用它的 8 邻域跟它自己比,比它亮记 1、暗记 0,
             按顺序拼成 8 位二进制数 (= 0~255 的整数),作为这个像素的"纹理编码"。
        返回:跟原图尺寸差不多的 LBP 图 (去掉最外圈像素,所以尺寸 h-2 x w-2)
        """
        h, w = gray_image.shape
        # 初始化 LBP 矩阵,比原图小一圈(因为最外圈没有完整 8 邻域)
        lbp = np.zeros((h-2, w-2), dtype=np.float32)

        # 遍历每个像素 (从 [1, h-1) 和 [1, w-1),跳过最外圈)
        for i in range(1, h-1):
            for j in range(1, w-1):
                center = gray_image[i, j]   # 当前像素的灰度值
                code = 0                     # 8 位编码从 0 开始拼
                # 按固定方向顺序检查 8 个邻居,亮=1,暗=0,左移对应位数再或上
                code |= (gray_image[i-1, j-1] > center) << 7  # 左上角,bit7
                code |= (gray_image[i-1, j]   > center) << 6  # 正上,bit6
                code |= (gray_image[i-1, j+1] > center) << 5  # 右上,bit5
                code |= (gray_image[i,   j+1] > center) << 4  # 正右,bit4
                code |= (gray_image[i+1, j+1] > center) << 3  # 右下,bit3
                code |= (gray_image[i+1, j]   > center) << 2  # 正下,bit2
                code |= (gray_image[i+1, j-1] > center) << 1  # 左下,bit1
                code |= (gray_image[i,   j-1] > center) << 0  # 正左,bit0
                lbp[i-1, j-1] = code  # 把这个像素的 LBP 编码存到结果图里

        return lbp

    def extract_all_features(self, image):
        """
        提取所有四种特征并拼接成一个长向量。
        用于 EnsembleClassifier 的 'all' 字段,做"一整条 2329 维特征向量"识别。
        """
        # 如果是彩色图,提取灰度版本给视觉/变换/代数三类使用
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 分别调 4 个 extractor
        visual = self.extract_visual_features(gray)         # HOG, 1764 维
        statistics = self.extract_pixel_statistics(image)  # 像素统计, 14 维 (传彩色,因为里面会自己取彩色直方图)
        transform = self.extract_transform_features(gray)   # DCT+PCA+DFT, 528 维
        algebraic = self.extract_algebraic_features(gray)   # SVD+范数+LBP, 23 维

        # np.concatenate 沿 axis=0 拼成一个长向量
        all_features = np.concatenate([
            visual,
            statistics,
            transform,
            algebraic
        ])

        return all_features

    def get_feature_dimension(self, feature_type='all'):
        """
        获取指定特征类型的维度 (与 extract_* 方法返回值严格一致)
        用途:前端 /api/features 接口展示特征维度,以及录入/识别时分配存储空间。
        """
        if feature_type == 'visual':
            return 1764  # HOG
        elif feature_type == 'statistics':
            return 14   # Pixel Stats (灰度5 + 直方图3 + 彩色6)
        elif feature_type == 'transform':
            return 528  # DCT 256 + PCA 16 + DFT 256
        elif feature_type == 'algebraic':
            return 23   # SVD 16 + 范数 4 + 迹 1 + LBP 2
        else:  # all / ensemble
            return 1764 + 14 + 528 + 23  # = 2329


class EnsembleClassifier:
    """
    融合四种特征的分类器 (实验模块)
    用 4 种手工特征 (HOG / Pixel / Transform / Algebraic) 分别算相似度,
    再按权重加权求和,得到最终判定。

    与主流程 face_recognition_core.py 的区别:
      - 主流程: dlib ResNet (深度学习, 128 维)
      - 这里:   4 种传统手工特征 (合计 2329 维) + 加权融合

    答辩演示用: 同一个识别任务,ResNet 准确率高,手工特征融合作为对照组。
    """

    def __init__(self, feature_extractor):
        self.feature_extractor = feature_extractor
        # known_features 是个 list,每个元素是一个 dict,存一个人 5 种特征向量
        self.known_features = []  # [{visual, statistics, transform, algebraic, all}, ...]
        # known_names 跟 known_features 一一对应,存姓名
        self.known_names = []
        # 4 种特征的权重,加起来 = 1
        # 视觉 (HOG) 权重最高 (0.4) —— 在传统方法里精度最稳
        # 像素统计 (0.1) 最低 —— 信息量少,只做辅助
        self.feature_weights = {
            'visual': 0.4,
            'statistics': 0.1,
            'transform': 0.25,
            'algebraic': 0.25
        }

    def add_person(self, name, image):
        """
        录入一个新人:用 image 算出 5 种特征,存到内存库。
        (注:不像 face_recognition_core 那样支持多张图取平均,这里一次录入一张)
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 5 种特征分开存,后面识别时分别算相似度再加权
        features = {
            'visual': self.feature_extractor.extract_visual_features(gray),
            'statistics': self.feature_extractor.extract_pixel_statistics(image),
            'transform': self.feature_extractor.extract_transform_features(gray),
            'algebraic': self.feature_extractor.extract_algebraic_features(gray),
            'all': self.feature_extractor.extract_all_features(image)
        }

        self.known_features.append(features)  # 追加到库
        self.known_names.append(name)

    def recognize(self, image, threshold=0.6):
        """
        融合特征识别:返回 (姓名, 相似度)
        阈值 threshold:相似度低于它就判定 Unknown
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 同样算 5 种特征
        features = {
            'visual': self.feature_extractor.extract_visual_features(gray),
            'statistics': self.feature_extractor.extract_pixel_statistics(image),
            'transform': self.feature_extractor.extract_transform_features(gray),
            'algebraic': self.feature_extractor.extract_algebraic_features(gray),
            'all': self.feature_extractor.extract_all_features(image)
        }

        # 如果库是空的,直接 Unknown
        if len(self.known_features) == 0:
            return 'Unknown', 0.0

        # 收集每个人跟查询图的加权相似度
        weighted_similarities = []

        for known in self.known_features:
            # 各种特征分别算余弦相似度
            # 注:这里 sim_all 也算了但最后加权没用到 (权重表里没有 'all' 这一项),
            #     相当于冗余存储、留作扩展
            sim_visual = self._cosine_similarity(features['visual'], known['visual'])
            sim_statistics = self._cosine_similarity(features['statistics'], known['statistics'])
            sim_transform = self._cosine_similarity(features['transform'], known['transform'])
            sim_algebraic = self._cosine_similarity(features['algebraic'], known['algebraic'])
            sim_all = self._cosine_similarity(features['all'], known['all'])

            # 加权平均 (只用了 4 种,'all' 留作扩展)
            weighted_sim = (
                sim_visual * self.feature_weights['visual'] +
                sim_statistics * self.feature_weights['statistics'] +
                sim_transform * self.feature_weights['transform'] +
                sim_algebraic * self.feature_weights['algebraic']
            )

            weighted_similarities.append(weighted_sim)

        # 找最大相似度对应的人
        max_idx = np.argmax(weighted_similarities)
        max_sim = weighted_similarities[max_idx]

        # 低于阈值就 Unknown
        if max_sim < threshold:
            return 'Unknown', max_sim

        return self.known_names[max_idx], max_sim

    def _cosine_similarity(self, a, b):
        """
        余弦相似度 (Cosine Similarity)
        公式: cos(θ) = (a·b) / (|a| * |b|)
        范围: [-1, 1], 越接近 1 越相似
        优点:跟向量长度无关,只看"方向",对光照/曝光变化比欧氏距离鲁棒。
        """
        # 确保输入是 numpy 数组,float32 类型
        a = np.array(a, dtype=np.float32)
        b = np.array(b, dtype=np.float32)

        # np.linalg.norm 默认是 L2 范数 (= 欧氏长度)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        # 防御:如果其中一个向量全 0 (norm 为 0),返回 0 而不是 NaN/Inf
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0

        # 点积除以两个模的乘积 = cos θ
        return np.dot(a, b) / (norm_a * norm_b)