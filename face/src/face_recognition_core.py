"""
Face Recognition Core Module
============================
实现人脸识别系统的核心功能:检测、预处理、特征提取、识别。
包括 4 个标准环节:
    1. 人脸图像采集及检测        (dlib HOG+SVM 检测器)
    2. 人脸图像预处理           (7 个原子操作 + 管线调度)
    3. 人脸图像特征提取          (dlib ResNet, 128 维)
    4. 匹配与识别              (欧氏距离 + 阈值 0.6)

[v2 bug-fix] 录入和识别都做 L2 归一化,避免欧氏距离虚高。
"""
import numpy as np
import cv2
import dlib
import os

# 项目根目录:无论从哪里启动,都基于本文件(src/face_recognition_core.py)向上找一级
# 假设文件结构: 项目根/{src, models, data, ...}
# os.path.abspath(__file__) → 当前文件的绝对路径 (如 F:\face\src\face_recognition_core.py)
# os.path.dirname(...)       → F:\face\src
# 再 dirname 一次             → F:\face
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# dlib 预训练模型存放目录 (detector / predictor / face_model)
MODELS_DIR = os.path.join(PROJECT_ROOT, 'models')
# 人脸库和记录存放目录 (npz / json)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')


class FaceRecognitionCore:
    """人脸识别核心类:整套系统的大脑,封装所有识别相关逻辑"""

    def __init__(self):
        """
        初始化:加载 dlib 提供的 3 个预训练模型。
        这些模型都来自 dlib 官方(http://dlib.net/),在 LFW 数据集上训练。
        """
        # 1. 人脸检测器 (HOG + SVM 滑窗),只能检正面脸,无需额外模型文件
        # 训练数据 dlib 自带,不需要 .dat
        self.detector = dlib.get_frontal_face_detector()

        # 2. 关键点检测器:给定一张脸,返回 68 个关键点 (眼/鼻/嘴/下颌轮廓)
        # 需要 .dat 模型文件,~95MB
        self.predictor = dlib.shape_predictor(
            os.path.join(MODELS_DIR, 'shape_predictor_68_face_landmarks.dat'))

        # 3. 人脸特征提取模型:ResNet,输入对齐后的 150x150 人脸,输出 128 维特征向量
        # 需要 .dat 模型文件,~22MB
        self.face_model = dlib.face_recognition_model_v1(
            os.path.join(MODELS_DIR, 'dlib_face_recognition_resnet_model_v1.dat'))

        # 已知人脸库 (内存里):每个元素是 128 维 numpy 向量
        self.known_faces = []
        # 对应姓名,跟 known_faces 一一对应 (下标同步)
        self.known_names = []
        # 特征历史(预留,当前没用到)
        self.feature_history = {}

        # 启动时自动加载数据库 (npz + 同步元数据 json)
        # 之前是手动调 core.load_database(), 容易忘记导致数据不一致
        self.load_database()

    def imread(self, path):
        """
        读取图片,支持中文路径。
        OpenCV 自带的 cv2.imread 在 Windows 上遇到中文路径会返回 None,
        所以这里用 np.fromfile + cv2.imdecode 组合绕过这个问题。
        """
        try:
            # 把文件当成 uint8 字节流读进来 (np.fromfile 不受路径编码影响)
            data = np.fromfile(path, dtype=np.uint8)
            # imdecode 把字节流解码成图片数组 (BGR 格式)
            # IMREAD_COLOR = 强制读为 3 通道彩色图
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            return img
        except Exception:
            # 任何异常 (文件不存在 / 不是图片 / 损坏) 都返回 None
            return None

    # ==================== 人脸检测 ====================
    def detect_faces(self, gray_image):
        """
        检测图片中的人脸位置。
        :param gray_image: 灰度图 (单通道)
        :return: dlib.rectangles 列表,每项是一个矩形 (left/top/right/bottom)
        """
        # 调用 dlib 检测器,第 2 个参数是上采样次数,1 表示不做额外放大
        # (摄像头实时一般用 2,提升小脸检出率)
        faces = self.detector(gray_image, 1)
        return faces

    def get_face_landmarks(self, rgb_image, face_rect):
        """
        获取一张脸的 68 个关键点坐标。
        :param rgb_image: RGB 图 (dlib 要 RGB,不是 BGR)
        :param face_rect: detect_faces 返回的某个矩形
        :return: dlib.full_object_detection,包含 68 个 (x, y) 点
        """
        shape = self.predictor(rgb_image, face_rect)
        return shape

    # ==================== 图像预处理 ====================
    # 下面 7 个独立原子操作:每个只做一件事,可被单独调用,也可被组合方法调度。
    # 设计动机:之前是写死 7 步顺序,改起来麻烦;改成原子操作 + 管线调度更灵活。

    def light_compensation(self, img):
        """
        光线补偿 —— 基于 LAB 空间的亮度调整
        目的:不同光照下拍出来的脸亮度差异很大,把整体亮度拉到接近 128 (中间值)。
        LAB 空间:L 是亮度通道,A/B 是色度通道,只调 L 不影响颜色。
        """
        # BGR → LAB (L:亮度, A:绿红, B:蓝黄)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        # 拆成 L/A/B 三个通道
        l, a, b = cv2.split(lab)
        # 算 L 通道的平均亮度
        mean_l = np.mean(l)
        # 把 L 整体乘以 128/mean_l,让均值变 128
        # max(mean_l, 1) 防止全黑图除 0
        # np.clip 限制到 [0, 255] (像素值范围),astype 转回 uint8
        l = np.clip(l * (128 / max(mean_l, 1)), 0, 255).astype(np.uint8)
        # 三个通道重新合并,再转回 BGR
        lab = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def gray_transform(self, img):
        """
        灰度变换 —— 亮度拉伸 (线性归一化)
        目的:把整张图的灰度范围从 [min, max] 拉到 [0, 255],增强对比度。
        """
        # 先转灰度
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 线性变换增强对比度
        min_val, max_val = gray.min(), gray.max()
        if max_val > min_val:
            # 公式:out = (in - min) * 255 / (max - min)
            # 效果:最暗→0, 最亮→255, 中间按比例拉伸
            gray = ((gray - min_val) * 255 / (max_val - min_val)).astype(np.uint8)
        return gray

    def histogram_equalization(self, img):
        """
        直方图均衡化 —— 增强对比度
        原理:把灰度直方图从"集中在某个区间"摊平成"均匀铺满 0~255"。
        彩色图先转 YUV,只对 Y(亮度)通道做均衡,色度通道保持。
        """
        if len(img.shape) == 3:
            # 彩色图:BGR → YUV,只动 Y 通道 (亮度)
            yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
            yuv[:, :, 0] = cv2.equalizeHist(yuv[:, :, 0])  # 均衡化亮度
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)     # 转回 BGR
        else:
            # 已经是灰度图,直接均衡化
            return cv2.equalizeHist(img)

    def normalization(self, img, target_range=(0, 255)):
        """
        归一化 —— 把像素值线性映射到指定范围
        跟 gray_transform 类似,只是目标范围可以指定,默认 [0, 255]。
        """
        min_val, max_val = img.min(), img.max()
        if max_val > min_val:
            # 通用公式:(in - min) / (max - min) * (new_max - new_min) + new_min
            normalized = (img - min_val) * (target_range[1] - target_range[0]) / (max_val - min_val)
            return normalized.astype(np.uint8)
        # 如果图全是一个值,直接返回原图 (避免除 0)
        return img

    def geometric_correction(self, img, shape):
        """
        几何校正 —— 人脸对齐
        原理:用 dlib 提供的 get_face_chip,以两眼中心为基准做仿射变换,
             把人脸"摆正"成正面,输出 150x150 标准化图。
        为什么需要:同一个人侧脸/抬头/低头,拍出来像素位置差很远,
                  不对齐的话特征差距会很大,对齐后特征才稳定。
        """
        # size=150 输出 150x150 大小
        face_chip = dlib.get_face_chip(img, shape, size=150)
        return face_chip

    def filtering(self, img, kernel_size=3):
        """
        滤波 —— 高斯模糊去噪
        目的:去掉摄像头噪点 / JPEG 压缩伪影。
        高斯模糊:用高斯函数做卷积,边缘保留比均值模糊好。
        """
        # (kernel_size, kernel_size) 高斯核大小 (奇数),0 表示标准差自动算
        return cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)

    def sharpening(self, img):
        """
        锐化 —— 增强边缘
        原理:用一个 3x3 锐化卷积核,中心权重 9,四周 -1,
             等价于"原图 × 9 - 周围一圈",放大高频成分。
        注意:对彩色图每个通道都做,所以颜色不变。
        """
        # 锐化卷积核:中心 9,周围 -1,总和 = 1 (不会改变整体亮度)
        kernel = np.array([[-1, -1, -1],
                           [-1,  9, -1],
                           [-1, -1, -1]])
        # filter2D 卷积, ddepth=-1 表示输出跟输入同类型
        return cv2.filter2D(img, -1, kernel)

    # 组合预处理管线: 通过 steps 列表按需组合原子操作
    # 替代原 preprocess_face_full / preprocess_face 的硬编码方式
    def apply_preprocess_pipeline(self, img, steps, shape=None):
        """
        按 steps 顺序串接原子操作。
        :param img: 输入图像 (BGR 或 RGB, 内部根据 steps 自动适配)
        :param steps: 列表, 每项是 (name, kwargs) 形式的元组
                      支持的 name: light_compensation, gray_transform,
                                  histogram_equalization, normalization,
                                  filtering, sharpening, geometric_correction
                      特殊: 'align' 一步走 dlib.get_face_chip, 需要 shape
        :param shape: dlib full_object_detection, geometric_correction / align 需要
        :return: 处理后的图像 (numpy ndarray)
        """
        out = img
        # 遍历每一步,串接调用
        for step in steps:
            # 防御性检查:每项必须是 (name, kwargs) 形式的二元元组
            if not isinstance(step, tuple) or len(step) != 2:
                raise ValueError(f"steps 每项必须是 (name, kwargs) 元组, 收到: {step!r}")
            name, kwargs = step
            if name == 'align':
                # 简化调用,等价于 geometric_correction 但语义更明确
                if shape is None:
                    raise ValueError("'align' 步骤需要 shape 参数")
                out = self.geometric_correction(out, shape)
            elif name == 'geometric_correction':
                if shape is None:
                    raise ValueError("'geometric_correction' 步骤需要 shape 参数")
                out = self.geometric_correction(out, shape)
            else:
                # 用 getattr 动态拿到对应方法 (例如 name='filtering' → self.filtering)
                method = getattr(self, name, None)
                # 黑名单:这几个方法不是预处理步骤,不允许通过管线调用
                # (防止不小心把 detect_faces/extract_features 塞进预处理管线)
                if method is None or name in ('detect_faces', 'get_face_landmarks',
                                              'imread', 'extract_features',
                                              'extract_features_with_preprocess',
                                              'preprocess_face_full', 'preprocess_face',
                                              'apply_preprocess_pipeline'):
                    raise ValueError(f"未知的预处理步骤: {name!r}")
                # 有 kwargs 就解包传,没有就只传图
                out = method(out, **kwargs) if kwargs else method(out)
        return out

    # 完整管线: 适用于训练/录入场景, 全部 7 步
    # 顺序: 光线补偿 → 对齐 → 直方图均衡 → 归一化 → 滤波 → 锐化 → 再均衡
    PREPROCESS_PIPELINE_FULL = [
        ('light_compensation', {}),
        ('geometric_correction', {}),       # 占位, 调用时需 shape
        ('histogram_equalization', {}),
        ('normalization', {}),
        ('filtering', {'kernel_size': 3}),
        ('sharpening', {}),
        ('histogram_equalization', {}),
    ]

    # 简化管线: 适用于识别场景, 3 步(对齐 + 直方图 + 滤波)
    # 比 FULL 快很多,识别时不需要那么复杂的增强
    PREPROCESS_PIPELINE_FAST = [
        ('align', {}),
        ('histogram_equalization', {}),
        ('filtering', {'kernel_size': 3}),
    ]

    def preprocess_face_full(self, img, face_rect):
        """
        完整人脸预处理流程 (7 步, 通过管线调度)
        用于训练/录入场景, 增强特征稳定性。
        :param img: BGR 彩色图
        :param face_rect: detect_faces 返回的人脸矩形
        :return: (处理后 RGB 图, 68 关键点 shape)
        """
        # dlib predictor 需要 RGB 图
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # 先拿 68 关键点,后面给几何校准用
        shape = self.get_face_landmarks(rgb_img, face_rect)
        # 走 7 步管线
        out = self.apply_preprocess_pipeline(
            img, self.PREPROCESS_PIPELINE_FULL, shape=shape)
        # 转回 RGB 返回 (历史接口约定,后面 ResNet 还要再转一次回 RGB)
        return cv2.cvtColor(out, cv2.COLOR_BGR2RGB), shape

    def preprocess_face(self, img, shape):
        """
        简化预处理: 对齐 + 直方图均衡 + 滤波 (3 步, 通过管线调度)
        用于识别场景, 平衡速度与质量。
        """
        out = self.apply_preprocess_pipeline(
            img, self.PREPROCESS_PIPELINE_FAST, shape=shape)
        # 兼容原行为: 返回 RGB (历史接口约定)
        return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)

    # ==================== 特征提取 (bug-fix: 两边都 L2 归一化) ====================
    def _l2_normalize(self, vec):
        """
        L2 归一化到单位向量, 避免 norm 不一致导致欧氏距离虚高。
        公式:vec_normalized = vec / ||vec||_2
        效果:归一化后所有特征向量都在单位球面上,||vec||=1,
             这样欧氏距离 d ∈ [0, 2] 范围固定,阈值 0.6 才有意义。
        """
        n = np.linalg.norm(vec)  # 欧氏范数 (L2)
        # 防御:全 0 向量除 0 会爆,直接返回原向量
        return vec / n if n > 1e-10 else vec

    @staticmethod
    def _distance_to_similarity(distance):
        """
        距离 → 相似度,clamp 到 [0, 1]。

        原公式 similarity = 1 - distance, 范围 [-1, 1] 有物理问题:
          - 距离 0:  相似度 1.0 (完全相同)
          - 距离 0.6: 相似度 0.4 (dlib 阈值边, 同一人边界)
          - 距离 1.0: 相似度 0  (正交)
          - 距离 1.5: 相似度 -0.5 (反向量, 不该出现)
          - 距离 2.0: 相似度 -1.0 (反向量)

        修复:clamp 到 [0, 1], 负值压到 0, 避免前端显示 "相似度 -50%" 这种误导。
        """
        return max(0.0, 1.0 - distance)

    def extract_features(self, rgb_image, face_rect):
        """
        提取人脸特征 (128 维向量,已 L2 归一化)。
        :param rgb_image: RGB 图
        :param face_rect: 人脸矩形
        :return: 128 维 numpy 向量 (单位向量, ||v||=1)
        """
        # 1. 关键点检测
        shape = self.predictor(rgb_image, face_rect)
        # 2. ResNet 推理得到 128 维描述子
        # 第 3 个参数 = 1 表示采样 1 次 (默认是 10,越多次越准但越慢)
        face_descriptor = self.face_model.compute_face_descriptor(
            rgb_image, shape, 1)
        # 3. 转 numpy + L2 归一化
        return self._l2_normalize(np.array(face_descriptor))

    def extract_features_with_preprocess(self, rgb_image, face_rect):
        """
        带预处理的特征提取 (已 L2 归一化)。

        处理流程:
          1. dlib 关键点定位 (68 点)
          2. 走 PREPROCESS_PIPELINE_FAST 管线 (对齐 + 直方图均衡 + 滤波)
          3. ResNet 推理 → 128 维
          4. L2 归一化
        """
        # 1. 关键点 (需要原始 RGB 给 predictor)
        shape = self.predictor(rgb_image, face_rect)
        # 2. 走 3 步管线 (dlib.get_face_chip 内嵌于 align 步骤)
        # 注意: preprocess_face 内部要求 BGR 输入, 这里先转 BGR 再转回 RGB
        bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
        processed_bgr = self.preprocess_face(bgr, shape)
        # processed_bgr 实际是 BGR (管线返回 BGR, 末尾 cv2.cvtColor 转 RGB 拿回)
        # 但 ResNet 要求 RGB 输入, 所以再转一次
        processed_rgb = cv2.cvtColor(processed_bgr, cv2.COLOR_BGR2RGB)
        # 3. ResNet 推理
        face_descriptor = self.face_model.compute_face_descriptor(
            processed_rgb, shape, 1)
        # 4. L2 归一化
        return self._l2_normalize(np.array(face_descriptor))

    # ==================== 人脸识别 ====================
    def recognize_face(self, face_descriptor, th=0.6):
        """
        辨认 (一对多):识别待识别人脸是谁。
        :param face_descriptor: 待识别的 128 维特征 (L2 归一化)
        :param th: 阈值,欧氏距离 < th 算同一个人,dlib 官方推荐 0.6
        :return: (姓名, 相似度, 模式字符串)
        """
        if len(self.known_faces) == 0:
            return 'Unknown', 0.0, 'identification'

        # numpy 广播:known_faces 是 (N, 128),face_descriptor 是 (128,)
        # 相减后 shape = (N, 128),沿 axis=1 求范数得到 (N,) 距离向量
        distances = np.linalg.norm(
            self.known_faces - face_descriptor, axis=1)
        # 取距离最小的下标和距离
        min_idx = np.argmin(distances)
        min_distance = distances[min_idx]
        # 距离 → 相似度 (clamp 到 [0,1])
        similarity = self._distance_to_similarity(min_distance)

        # 阈值判断:小于 th 算匹配,否则 Unknown
        if min_distance < th:
            return self.known_names[min_idx], similarity, 'identification'
        return 'Unknown', similarity, 'identification'

    def verify_face(self, face_descriptor, person_name, th=0.6):
        """
        确认 (一对一):验证待识别人脸是不是 person_name。
        :param face_descriptor: 待确认的 128 维特征
        :param person_name: 目标姓名
        :param th: 阈值
        :return: (是否匹配, 相似度, 模式字符串)
        """
        if len(self.known_faces) == 0:
            return False, 0.0, 'verification'

        # 库里有这个人吗?
        if person_name not in self.known_names:
            return False, 0.0, 'verification'

        # .index() 找该姓名在列表里的下标
        idx = self.known_names.index(person_name)
        # 取对应的 128 维特征
        known_descriptor = self.known_faces[idx]
        # 算欧氏距离
        distance = np.linalg.norm(known_descriptor - face_descriptor)
        similarity = self._distance_to_similarity(distance)

        # 距离 < th 算同一个人
        is_match = distance < th
        return is_match, similarity, 'verification'

    def identify_face(self, face_descriptor, th=0.6):
        """
        辨认 (一对多,完整版):返回所有匹配结果,按相似度排序。
        跟 recognize_face 的区别:这个返回所有通过阈值的人,不只是最像的那个。
        用于前端展示"前 N 个候选人"。
        """
        if len(self.known_faces) == 0:
            return [], 'identification'

        # 算库中每个人跟查询的欧氏距离
        distances = np.linalg.norm(
            self.known_faces - face_descriptor, axis=1)

        # 按距离排序,返回所有结果
        results = []
        for i, dist in enumerate(distances):
            similarity = self._distance_to_similarity(dist)
            if dist < th:  # 只收距离小于阈值的 (同一人判定)
                results.append({
                    'name': self.known_names[i],
                    'similarity': similarity,
                    'distance': dist
                })

        # 按相似度降序排序 (最像的排前面)
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results, 'identification'

    # ==================== 人员管理 ====================
    def _add_person_internal(self, name, image_paths, extractor):
        """
        录入人员内部实现: 抽取两张图的共同逻辑, 用 extractor 参数选择特征提取方式。

        :param name: 人员姓名
        :param image_paths: 图片路径列表 (通常 1~多张)
        :param extractor: 特征提取函数, 签名 (rgb_image, face_rect) -> np.ndarray
                          可选: self.extract_features 或 self.extract_features_with_preprocess
        :return: True (录入成功) / False (所有图都未检测到人脸)
        """
        features_list = []  # 收集每张图提取出的 128 维特征
        for img_path in image_paths:
            # 用支持中文路径的 imread
            img = self.imread(img_path)
            if img is None:
                continue  # 读不出来的图跳过
            # 同时准备 RGB (给特征提取) 和 GRAY (给人脸检测)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # 检测人脸
            faces = self.detect_faces(img_gray)
            if len(faces) == 0:
                continue  # 这张图没脸,跳过
            # 用传入的 extractor 替代硬编码 (消除 add_person / add_person_with_preprocess 重复)
            # 取最大那张脸 (faces[0],dlib 默认按面积排序)
            features = extractor(img_rgb, faces[0])
            features_list.append(features)

        # 如果一张图都没提成功,返回 False
        if len(features_list) == 0:
            return False

        # 多张图的特征取平均,得到一个更稳定的 128 维特征向量
        # 多次录入可以减少单张图噪声的影响
        avg_features = np.mean(features_list, axis=0)
        # 再做一次 L2 归一化 (因为平均向量长度可能不是 1)
        avg_features = self._l2_normalize(avg_features)
        # 加入内存库
        self.known_faces.append(avg_features)
        self.known_names.append(name)
        return True

    def add_person(self, name, image_paths):
        """
        添加人员: 不走预处理管线, 直接 dlib 关键点 + ResNet 推理。
        适用场景: 原图已经质量好, 不需要额外增强。
        """
        return self._add_person_internal(name, image_paths, self.extract_features)

    def add_person_with_preprocess(self, name, image_paths):
        """
        添加人员: 走 3 步预处理管线 (对齐+直方图+滤波) + ResNet 推理。
        适用场景: 录入质量参差的图, 预处理增强稳定性。
        """
        return self._add_person_internal(name, image_paths, self.extract_features_with_preprocess)

    def remove_person(self, name):
        """
        仅修改内存: 从 known_faces/known_names 列表中删除。
        落盘请用 remove_person_and_persist (避免 npz/json 不一致)。
        """
        if name not in self.known_names:
            return False
        # 用 .index 找下标,pop 同时从两个列表删,保证下标对应
        idx = self.known_names.index(name)
        self.known_faces.pop(idx)
        self.known_names.pop(idx)
        return True

    def remove_person_and_persist(self, name):
        """
        删除人员并落盘 (npz + json 同步)。
        返回 (success: bool, message: str)。
        """
        if name not in self.known_names:
            return False, f'{name} 不存在'
        try:
            self.remove_person(name)
            # 落盘:npz + 自动同步 json 元数据
            self.save_database()
            return True, f'已删除 {name}'
        except Exception as e:
            # 异常时内存可能已经改了,这里简单打印错误信息 (实际生产应该回滚)
            return False, f'删除失败: {e}'

    # ==================== 数据库管理 (npz + json 同步) ====================
    # 单一 source of truth: face_database.npz (128 维特征)
    # face_db.json 是派生元数据, 由 sync_metadata_from_npz() 从 npz 重建
    # 这样设计的好处:不会出现"npz 和 json 数量对不上"的不一致问题
    META_JSON_PATH = os.path.join(DATA_DIR, 'face_db.json')

    def load_database(self, db_path=None):
        """
        加载数据库:
          1. 读 npz (source of truth,128 维特征)
          2. 自动重建 face_db.json 元数据 (如果缺失或数量对不上)
        """
        if db_path is None:
            db_path = os.path.join(DATA_DIR, 'face_database.npz')
        if os.path.exists(db_path):
            # np.load 默认返回 NpzFile 对象,像字典一样用 ['key'] 取数组
            data = np.load(db_path)
            # 转成 list 存到 self 上 (后续识别需要迭代)
            self.known_faces = list(data['faces'])
            self.known_names = list(data['names'])
            # 自动同步元数据 json (修复可能的不一致)
            self.sync_metadata_from_npz()
            return True
        return False

    def save_database(self, db_path=None):
        """
        保存 npz (source of truth) + 同步重建 face_db.json。
        """
        if db_path is None:
            db_path = os.path.join(DATA_DIR, 'face_database.npz')
            # makedirs(..., exist_ok=True) — 目录不存在就建,已存在不报错
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # np.savez 把多个数组打包存成 .npz 压缩格式
        # faces: 128 维特征矩阵 (N x 128)
        # names: 姓名字符串数组 (N,)
        np.savez(db_path,
                 faces=np.array(self.known_faces),
                 names=np.array(self.known_names))
        # 落盘后立即同步元数据
        self.sync_metadata_from_npz()

    def sync_metadata_from_npz(self, json_path=None):
        """
        从内存中的 known_faces/known_names 重建 face_db.json 元数据。
        消除冗余: 之前 json 里存的 features 数组跟 npz 重复, 改存元数据。
        元数据 (image_path, add_time) 用 stub 占位 (录入接口可补充)。
        """
        # 在函数内部 import 避免循环引用
        import json as _json
        from datetime import datetime as _dt
        if json_path is None:
            json_path = self.META_JSON_PATH

        # 读旧 json, 提取 name -> 元数据 映射 (保留已有 image_path/add_time)
        old_meta = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    old = _json.load(f)
                for entry in old:
                    if 'name' in entry:
                        old_meta[entry['name']] = {
                            k: v for k, v in entry.items()
                            if k not in ('features',)  # 丢弃 features 字段 (npz 才是 source of truth)
                        }
            except Exception:
                # 旧 json 损坏也不影响启动,直接当成空
                pass

        # 用当前内存状态重建
        new_meta = []
        for name in self.known_names:
            if name in old_meta:
                # 已有元数据,沿用 (保留 image_path/add_time)
                entry = old_meta[name].copy()
                entry['name'] = name
            else:
                # 新人,给个默认元数据
                entry = {
                    'name': name,
                    'image_path': None,
                    'add_time': _dt.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
            new_meta.append(entry)

        # 落盘
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        # ensure_ascii=False — 中文不转 \u 编码,直接存 UTF-8
        # indent=2 — 缩进 2 空格,文件可读
        with open(json_path, 'w', encoding='utf-8') as f:
            _json.dump(new_meta, f, ensure_ascii=False, indent=2)

    # ==================== 视频帧处理 ====================
    def process_frame(self, frame, use_preprocess=True):
        """
        处理视频帧:检测 + 识别 + 画框 + 写字。
        用于摄像头实时演示场景。
        :param frame: BGR 图像 (单帧)
        :param use_preprocess: 是否走预处理 (默认 True)
        :return: (画好框的图, 结果列表)
        """
        # 同时准备 RGB (特征提取) 和 GRAY (检测)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # 检测人脸
        faces = self.detect_faces(gray_frame)
        results = []

        # 遍历每张检测到的脸
        for face_rect in faces:
            # 取矩形 4 个坐标 (left/top/right/bottom)
            left, top = face_rect.left(), face_rect.top()
            right, bottom = face_rect.right(), face_rect.bottom()

            # 使用预处理提取特征 (更稳)
            features = self.extract_features_with_preprocess(rgb_frame, face_rect)
            # 1:N 辨认,返回 (姓名, 相似度, 模式)
            name, confidence, mode = self.recognize_face(features)

            # 已知 → 绿框,未知 → 红框
            color = (0, 255, 0) if name != 'Unknown' else (0, 0, 255)
            # 画矩形框
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            # 框上方写字: "姓名:相似度百分比"
            # {confidence:.2%}  → 0.8715 → "87.15%"
            cv2.putText(frame, f'{name}:{confidence:.2%}',
                        (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, color, 2)

            # 把结果塞进 list,后面 API 返回 JSON 用
            results.append({
                'name': name,
                'confidence': confidence,
                'rect': (left, top, right, bottom),
                'mode': mode
            })

        # 返回画好的图 + 结构化结果
        return frame, results

    def process_frame_verification(self, frame, target_name, th=0.6):
        """
        处理视频帧做确认识别 (1:1)。
        跟 process_frame 的区别:这里只跟 target_name 比对,返回"匹配/不匹配"。
        """
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.detect_faces(gray_frame)
        results = []

        for face_rect in faces:
            left, top = face_rect.left(), face_rect.top()
            right, bottom = face_rect.right(), face_rect.bottom()

            # 确认场景走简单特征提取 (不做预处理,更快)
            features = self.extract_features(rgb_frame, face_rect)
            is_match, similarity, mode = self.verify_face(features, target_name, th)

            color = (0, 255, 0) if is_match else (0, 0, 255)
            status = "匹配" if is_match else "不匹配"
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.putText(frame, f'{target_name}:{status}({similarity:.2%})',
                        (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, color, 2)

            results.append({
                'match': is_match,
                'similarity': similarity,
                'rect': (left, top, right, bottom),
                'mode': mode
            })

        return frame, results
