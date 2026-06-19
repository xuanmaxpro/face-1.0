"""
Flask Web Application for Face Recognition System
=================================================
人脸识别系统 Web 前端 - Flask 后端。

本文件负责:
    1. 启动 Flask 服务
    2. 定义 14 个 API 路由 (主页 / 人员管理 / 录入 / 删除 / 识别 / 记录 / 特征 / ensemble)
    3. 串接前端 HTTP 请求到 FaceRecognitionCore / FeatureExtractor 等核心模块

启动方法:
    python src/main.py
启动后访问: http://localhost:5000

注意:本文件只关心"HTTP 接口怎么接",所有算法逻辑都在 src/ 包里。
"""
import os
import sys
import json
import time

from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np

# 把项目根目录加入 sys.path,这样能 import src.xxx
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 主识别核心 (dlib ResNet)
from src.face_recognition_core import FaceRecognitionCore, DATA_DIR
# 数据库/记录模块
from src.database import FaceDatabase, RecognitionRecord
# 4 种手工特征 + EnsembleClassifier
from src.feature_extractor import FeatureExtractor, EnsembleClassifier

# 创建 Flask 应用实例
# __name__ 让 Flask 知道模板/静态文件相对路径
app = Flask(__name__)


# ==================== 展示用相似度 helper ====================
# 用户要求: 前端展示的相似度统一显示成 0.90-1.00 之间的随机小数 (无整数)
# 不修改人脸识别逻辑 / 不修改 dlib / 不修改真实记录 (record.add_record 仍写真实值)
# 仅在 API 返回 JSON 时把真实 similarity 替换成展示用随机数
import random


def _display_similarity(real_similarity):
    """
    展示用相似度: 返回 [0.90, 1.00) 之间的随机小数, 保留 4 位小数 (避免整数)。
    :param real_similarity: 真实相似度 (0.0-1.0), 仅占位未使用。
    :return: 随机小数, 例 0.9234。
    """
    return round(random.uniform(0.90, 0.9999), 4)

# Flask 配置:session 加密密钥 (虽然本系统没用 session, 但 Flask 框架要求设置)
app.secret_key = 'face_recognition_secret_key_2024'
# 限制上传文件最大 16MB,防止恶意上传撑爆服务器
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 初始化核心模块 (这部分是单例,整个进程共用)
core = FaceRecognitionCore()           # dlib ResNet 识别器
db = FaceDatabase()                    # 人脸库元数据
record = RecognitionRecord()           # 识别记录
feature_extractor = FeatureExtractor() # 4 种手工特征提取器
ensemble_classifier = EnsembleClassifier(feature_extractor)  # 融合分类器

# 加载已有数据库 (npz)
core.load_database()


# ==================== 页面路由 ====================
@app.route('/')
def index():
    """主页 (渲染 templates/index.html)"""
    return render_template('index.html')


@app.route('/person')
def person_page():
    """人员管理页面 (渲染 templates/person.html)"""
    return render_template('person.html')


@app.route('/features')
def features_page():
    """特征介绍页面 (渲染 templates/features.html)"""
    return render_template('features.html')


# ==================== 统计与查询 API ====================
@app.route('/api/stats')
def get_stats():
    """获取统计信息:人数 / 记录数 / 姓名列表 (前端首页仪表盘用)"""
    return jsonify({
        'person_count': len(core.known_names),
        'record_count': len(record.records),
        'persons': core.known_names
    })


@app.route('/api/persons')
def get_persons():
    """获取所有人员姓名 (前端下拉列表用)"""
    return jsonify({
        'persons': core.known_names
    })


# ==================== 人员管理 API ====================
@app.route('/api/person/add', methods=['POST'])
def add_person():
    """
    添加人员 API。
    请求:multipart/form-data
        - name:   姓名 (表单字段)
        - images: 1~多张图片 (文件字段)
    返回:{'success': bool, 'message': str, 'person_count': int}
    """
    # 取姓名,strip() 去首尾空格
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '请输入姓名'})

    # getlist 拿所有同名 files (前端可能一次传多张)
    files = request.files.getlist('images')
    if not files or files[0].filename == '':
        return jsonify({'success': False, 'message': '请选择图片'})

    # ===== 保存到临时文件 =====
    # imread 需要文件路径,所以先把上传的字节流存成临时文件
    # 命名: temp_{毫秒时间戳}_{原文件名} → 防止并发时重名
    temp_paths = []
    for f in files:
        if f and f.filename:
            temp_path = f'temp_{int(time.time()*1000)}_{f.filename}'
            f.save(temp_path)
            temp_paths.append(temp_path)

    if not temp_paths:
        return jsonify({'success': False, 'message': '没有有效的图片文件'})

    # ===== 调核心模块录入 =====
    # add_person_with_preprocess 走 3 步预处理管线,比 add_person 更稳
    success = core.add_person_with_preprocess(name, temp_paths)

    # 清理临时文件 (不管成功失败都删)
    for path in temp_paths:
        if os.path.exists(path):
            os.remove(path)

    if success:
        # 用 core.save_database() 一并落盘 npz + 同步 face_db.json
        # (旧逻辑 db.add_face 会写冗余 features 到 json, 现在由 sync_metadata_from_npz 统一)
        core.save_database()
        # 元数据里的 image_path 单独补充
        if name in core.known_names:
            from src.face_recognition_core import FaceRecognitionCore
            FaceRecognitionCore.META_JSON_PATH  # 触发常量加载
        return jsonify({
            'success': True,
            'message': f'成功录入{name}的人脸数据',
            'person_count': len(core.known_names)
        })
    else:
        return jsonify({
            'success': False,
            'message': '未能检测到人脸，请重新选择图片'
        })


@app.route('/api/person/delete', methods=['POST'])
def delete_person():
    """删除人员 API (JSON body: {'name': '张三'})"""
    # get_json 解析 application/json 请求体
    data = request.get_json()
    name = data.get('name', '')

    if name not in core.known_names:
        return jsonify({'success': False, 'message': '人员不存在'})

    # 用 core.remove_person_and_persist 一并删除 + 落盘 (npz + json 同步)
    success, message = core.remove_person_and_persist(name)
    if success:
        return jsonify({
            'success': True,
            'message': message,
            'person_count': len(core.known_names)
        })
    return jsonify({'success': False, 'message': '删除失败'})


# ==================== 识别 API (核心功能) ====================
@app.route('/api/recognize', methods=['POST'])
def recognize():
    """
    识别图片中的人脸。
    支持两种模式:
        - identification (1:N 辨认):返回最像的库中人员
        - verification   (1:1 确认):跟指定人员比对,返回"是否同一人"
    """
    # ===== 解析请求参数 =====
    mode = request.form.get('mode', 'identification')   # 默认 1:N 辨认
    threshold = float(request.form.get('threshold', 0.6))  # 阈值
    target = request.form.get('target', '')             # 1:1 模式的目标姓名

    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': '请上传图片'})

    # ===== 读取图片 =====
    # file.read() 拿到字节流 → np.frombuffer 转 numpy 数组 → cv2.imdecode 解码成图片
    # 这套组合跟 cv2.imread 等价,但不需要先存盘
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)  # 强制读 3 通道彩色

    if img is None:
        return jsonify({'success': False, 'message': '无法读取图片'})

    # 同时准备 RGB (特征提取) 和 GRAY (人脸检测)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ===== 检测人脸 =====
    faces = core.detect_faces(img_gray)
    if len(faces) == 0:
        return jsonify({'success': False, 'message': '未检测到人脸', 'faces': []})

    # ===== 逐张脸处理 =====
    results = []
    for i, face_rect in enumerate(faces):
        # 取矩形坐标
        left, top = face_rect.left(), face_rect.top()
        right, bottom = face_rect.right(), face_rect.bottom()

        # 提取特征(使用预处理管线,更稳)
        features = core.extract_features_with_preprocess(img_rgb, face_rect)

        if mode == 'verification':
            # ===== 1:1 确认模式 =====
            if not target:
                return jsonify({'success': False, 'message': '请选择目标人员'})

            is_match, similarity, _ = core.verify_face(features, target, threshold)
            results.append({
                'face_id': i + 1,
                'name': target,
                'match': bool(is_match),   # bool() 把 numpy.bool_ 转成 Python bool,JSON 友好
                'similarity': _display_similarity(similarity),  # 用展示值,不暴露真实相似度
                'rect': [left, top, right, bottom]
            })
            # 记录里写"确认-张三" / "否认-张三" 方便后续统计区分
            record.add_record(f"确认-{target}" if bool(is_match) else f"否认-{target}", float(similarity))

        else:
            # ===== 1:N 辨认模式 =====
            matches, _ = core.identify_face(features, threshold)
            if matches:
                # 取最像的那个
                best = matches[0]
                results.append({
                    'face_id': i + 1,
                    'name': best['name'],
                    'similarity': _display_similarity(best['similarity']),
                    'rect': [left, top, right, bottom]
                })
                record.add_record(best['name'], float(best['similarity']))
            else:
                # 没匹配上,返回 Unknown
                results.append({
                    'face_id': i + 1,
                    'name': 'Unknown',
                    'similarity': 0.0,
                    'rect': [left, top, right, bottom]
                })
                record.add_record('Unknown', 0)

    return jsonify({
        'success': True,
        'mode': mode,
        'face_count': len(faces),
        'results': results
    })


# ==================== 识别记录 API ====================
@app.route('/api/records')
def get_records():
    """获取最近 limit 条识别记录 (默认 100)"""
    # request.args 取 URL query 参数 (?limit=200)
    limit = int(request.args.get('limit', 100))
    records = record.get_records(limit)
    return jsonify({
        'records': records,
        'total': len(record.records)
    })


@app.route('/api/records/clear', methods=['POST'])
def clear_records():
    """清空所有识别记录"""
    record.clear()
    return jsonify({'success': True, 'message': '记录已清空'})


@app.route('/api/persons/refresh', methods=['POST'])
def refresh_persons():
    """刷新人员列表 (从 npz 重新加载)"""
    core.load_database()
    return jsonify({
        'success': True,
        'persons': core.known_names,
        'count': len(core.known_names)
    })


# ==================== 特征展示 API (实验模块) ====================
@app.route('/api/features')
def get_feature_info():
    """
    获取支持的特征提取方法信息 (前端 features.html 展示用)。
    包含维度说明,跟 feature_extractor.py 里的 get_feature_dimension 保持一致。
    """
    return jsonify({
        'feature_types': [
            {'id': 'resnet', 'name': 'ResNet', 'description': '深度学习特征(128维)', 'dimension': 128},
            {'id': 'hog', 'name': 'HOG', 'description': '视觉特征-梯度方向直方图', 'dimension': 1764},
            {'id': 'pixel', 'name': 'Pixel Stats', 'description': '像素统计特征 (灰度5+直方图3+彩色6)', 'dimension': 14},
            {'id': 'transform', 'name': 'Transform', 'description': '变换系数特征(DCT256+PCA16+DFT256)', 'dimension': 528},
            {'id': 'algebraic', 'name': 'Algebraic', 'description': '代数特征(SVD16+范数5+LBP2)', 'dimension': 23},
            {'id': 'ensemble', 'name': 'Ensemble', 'description': '融合四种特征', 'dimension': 2329}
        ],
        'current_type': 'resnet'
    })


@app.route('/api/features/extract', methods=['POST'])
def extract_features():
    """
    提取单张图片的特征并返回 (供前端 features.html 实时可视化用)。
    支持 6 种特征类型:hog / pixel / transform / algebraic / ensemble / 默认(ResNet)
    """
    feature_type = request.form.get('feature_type', 'all')

    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': '请上传图片'})

    # 读图
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({'success': False, 'message': '无法读取图片'})

    # 准备灰度版
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    features = None
    feature_name = ''

    # 按类型分发到不同的 extractor
    if feature_type == 'hog':
        features = feature_extractor.extract_visual_features(gray)
        feature_name = 'HOG'
    elif feature_type == 'pixel':
        features = feature_extractor.extract_pixel_statistics(img)
        feature_name = 'Pixel Stats'
    elif feature_type == 'transform':
        features = feature_extractor.extract_transform_features(gray)
        feature_name = 'Transform'
    elif feature_type == 'algebraic':
        features = feature_extractor.extract_algebraic_features(gray)
        feature_name = 'Algebraic'
    elif feature_type == 'ensemble':
        features = feature_extractor.extract_all_features(img)
        feature_name = 'Ensemble'
    else:
        # 默认走 ResNet (深度学习)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        faces = core.detect_faces(gray)
        if len(faces) > 0:
            features = core.extract_features(img_rgb, faces[0])
            feature_name = 'ResNet'
        else:
            return jsonify({'success': False, 'message': '未检测到人脸'})

    return jsonify({
        'success': True,
        'feature_type': feature_name,
        'dimension': len(features),
        # 只返回前 10 维,数据量太大 (最多 2329) 容易拖慢前端
        'preview': features[:10].tolist() if len(features) > 10 else features.tolist()
    })


# ==================== EnsembleClassifier 端点 (实验模块) ====================
# 用途: 用 4 种手工特征 (HOG/Pixel/Transform/Algebraic) 融合识别, 跟 dlib ResNet 对比
# 答辩时可展示 "传统手工特征 vs 深度学习" 效果差异
# 数据独立存: ensemble_database.npz (跟主流程的 face_database.npz 不共享)
ENSEMBLE_DATA_FILE = os.path.join(DATA_DIR, 'ensemble_database.npz')


def _save_ensemble_db():
    """
    保存 ensemble_classifier 内存库到 npz (独立于 face_database.npz)。
    每种特征一个数组存,方便后续单独读。
    """
    # 三元表达式:库空就存空数组占位,shape (0, dim) 让 numpy 知道结构
    np.savez(ENSEMBLE_DATA_FILE,
             names=np.array(ensemble_classifier.known_names, dtype='U32'),  # Unicode 字符串,最长 32 字符
             visual=np.array([f['visual'] for f in ensemble_classifier.known_features], dtype=np.float32) if ensemble_classifier.known_features else np.zeros((0, 1764), dtype=np.float32),
             statistics=np.array([f['statistics'] for f in ensemble_classifier.known_features], dtype=np.float32) if ensemble_classifier.known_features else np.zeros((0, 20), dtype=np.float32),
             transform=np.array([f['transform'] for f in ensemble_classifier.known_features], dtype=np.float32) if ensemble_classifier.known_features else np.zeros((0, 304), dtype=np.float32),
             algebraic=np.array([f['algebraic'] for f in ensemble_classifier.known_features], dtype=np.float32) if ensemble_classifier.known_features else np.zeros((0, 50), dtype=np.float32),
             all=np.array([f['all'] for f in ensemble_classifier.known_features], dtype=np.float32) if ensemble_classifier.known_features else np.zeros((0, 2138), dtype=np.float32))


def _load_ensemble_db():
    """从 npz 恢复 ensemble_classifier 内存库"""
    if not os.path.exists(ENSEMBLE_DATA_FILE):
        return False
    # allow_pickle=True 兼容旧版本存的对象数组
    data = np.load(ENSEMBLE_DATA_FILE, allow_pickle=True)
    names = list(data['names'])
    if len(names) == 0:
        return False
    ensemble_classifier.known_names = names
    ensemble_classifier.known_features = []
    # 遍历每个人,按 dict 形式组装回内存结构
    for i in range(len(names)):
        ensemble_classifier.known_features.append({
            'visual': data['visual'][i],
            'statistics': data['statistics'][i],
            'transform': data['transform'][i],
            'algebraic': data['algebraic'][i],
            'all': data['all'][i],
        })
    return True


# 启动时尝试加载 ensemble 库
_load_ensemble_db()


@app.route('/api/ensemble/add', methods=['POST'])
def ensemble_add():
    """录入人员 (走 EnsembleClassifier, 用 4 种手工特征)"""
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '请输入姓名'})

    files = request.files.getlist('images')
    if not files or files[0].filename == '':
        return jsonify({'success': False, 'message': '请选择图片'})

    saved = 0
    for f in files:
        if not f or not f.filename:
            continue
        img_bytes = f.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            continue
        try:
            ensemble_classifier.add_person(name, img)
            saved += 1
        except Exception as e:
            # 单张图失败不影响其他,只打印日志
            print(f'录入失败: {e}')

    if saved > 0:
        _save_ensemble_db()
        return jsonify({
            'success': True,
            'message': f'已用 {saved} 张图片为 {name} 录入 ensemble 特征',
            'person_count': len(set(ensemble_classifier.known_names)),
        })
    return jsonify({'success': False, 'message': '未能从图片提取特征'})


@app.route('/api/ensemble/recognize', methods=['POST'])
def ensemble_recognize():
    """用 EnsembleClassifier 识别 (对比 ResNet)"""
    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': '请上传图片'})

    threshold = float(request.form.get('threshold', 0.6))

    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({'success': False, 'message': '无法读取图片'})

    # ensemble 库为空时友好提示
    if len(ensemble_classifier.known_features) == 0:
        return jsonify({
            'success': True,
            'method': 'ensemble',
            'name': 'Unknown',
            'similarity': 0.0,
            'message': 'ensemble 库为空, 请先通过 /api/ensemble/add 录入'
        })

    name, similarity = ensemble_classifier.recognize(img, threshold=threshold)
    return jsonify({
        'success': True,
        'method': 'ensemble',
        'name': name,
        'similarity': _display_similarity(similarity),
    })


@app.route('/api/ensemble/stats')
def ensemble_stats():
    """ensemble 库统计 (前端对比页面展示用)"""
    return jsonify({
        'person_count': len(set(ensemble_classifier.known_names)),
        'image_count': len(ensemble_classifier.known_names),
        'feature_weights': ensemble_classifier.feature_weights,
    })


if __name__ == '__main__':
    print("=" * 50)
    print("人脸识别系统 Web服务启动...")
    print("访问地址: http://localhost:5000")
    print("=" * 50)
    # host='0.0.0.0' 监听所有网卡 (局域网内可访问)
    # port=5000 Flask 默认端口
    # debug=True 开发模式:改代码自动重载 + 出错显示 traceback
    app.run(host='0.0.0.0', port=5000, debug=True)
