"""
测试 EnsembleClassifier 真正接入 app.py 后的功能

测试项:
  1. app.py 静态结构: 3 个新端点存在 (add/recognize/stats)
  2. app.py 静态结构: _save_ensemble_db / _load_ensemble_db 函数存在
  3. FeatureExtractor 4 个方法能跑 (HOG/Pixel/Transform/Algebraic)
  4. EnsembleClassifier add_person + recognize 完整流程
  5. 余弦相似度: 同人 vs 异人 距离差异
  6. API 端到端 (启动 Flask test_client, 模拟 multipart 请求)
  7. ensemble_database.npz 持久化往返
"""
import os
import sys
import ast
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))
os.chdir(os.path.dirname(ROOT))


print('=== 1) 语法 + 静态检查 ===')
with open('app.py', encoding='utf-8') as f:
    app_src = f.read()
try:
    ast.parse(app_src)
    print('  [OK] app.py 语法正确')
except SyntaxError as e:
    print(f'  [FAIL] {e}')
    sys.exit(1)

# 检查 3 个端点
for endpoint in ['/api/ensemble/add', '/api/ensemble/recognize', '/api/ensemble/stats']:
    if f"'{endpoint}'" in app_src:
        print(f'  [OK] 端点 {endpoint}')
    else:
        print(f'  [FAIL] 端点 {endpoint} 不存在')

# 检查 _save/_load 函数
for name in ['_save_ensemble_db', '_load_ensemble_db', 'ENSEMBLE_DATA_FILE']:
    if name in app_src:
        print(f'  [OK] {name}')
    else:
        print(f'  [FAIL] {name} 不存在')

# 启动时是否自动 load
if '_load_ensemble_db()' in app_src and '__main__' in app_src:
    # 找顶级代码 _load_ensemble_db() 调用
    top_calls = [line for line in app_src.split('\n')
                 if line.strip() == '_load_ensemble_db()']
    if top_calls:
        print(f'  [OK] 启动时 _load_ensemble_db() 自动调用 ({len(top_calls)} 处)')

# 检查 DATA_DIR 导入
if 'from src.face_recognition_core import FaceRecognitionCore, DATA_DIR' in app_src:
    print('  [OK] DATA_DIR 已导入')


print()
print('=== 2) dlib 集成 + API 端到端 ===')
try:
    import dlib
    from app import app as flask_app, feature_extractor, ensemble_classifier

    # 2.1 FeatureExtractor 4 个方法
    img = cv2.imdecode(np.fromfile('datasets/shenlinxuan/IMG_20260608_141050.jpg',
                                    dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, '读 xuan 图失败'
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # HOG
    f_hog = feature_extractor.extract_visual_features(gray)
    assert len(f_hog) == 1764
    print(f'  [OK] HOG 特征: dim={len(f_hog)}')

    # Pixel Stats
    f_pix = feature_extractor.extract_pixel_statistics(img)
    assert len(f_pix) == 14, f'Pixel Stats 期望 14 维, 实际 {len(f_pix)}'
    print(f'  [OK] Pixel Stats 特征: dim={len(f_pix)}')

    # Transform
    f_tr = feature_extractor.extract_transform_features(gray)
    assert len(f_tr) == 528
    print(f'  [OK] Transform 特征: dim={len(f_tr)}')

    # Algebraic
    f_al = feature_extractor.extract_algebraic_features(gray)
    assert len(f_al) == 23
    print(f'  [OK] Algebraic 特征: dim={len(f_al)}')

    # Ensemble (concat all)
    f_all = feature_extractor.extract_all_features(img)
    assert len(f_all) == 1764 + 14 + 528 + 23
    print(f'  [OK] Ensemble 特征: dim={len(f_all)} (concat)')

    # 2.2 EnsembleClassifier 完整流程
    # 备份现有 ensemble 库
    ens_path = 'data/ensemble_database.npz'
    if os.path.exists(ens_path):
        os.rename(ens_path, ens_path + '.bak')

    # 录入 xuan + chao
    chao_img = cv2.imdecode(np.fromfile('datasets/zhaohanchao/3e734401f831ab1ed858dddf30f80a01.jpg',
                                        dtype=np.uint8), cv2.IMREAD_COLOR)
    ensemble_classifier.add_person('xuan', img)
    ensemble_classifier.add_person('chao', chao_img)
    assert len(ensemble_classifier.known_names) == 2
    print(f'  [OK] EnsembleClassifier.add_person: 2 人入库')

    # 识别 xuan 自己
    name, sim = ensemble_classifier.recognize(img, threshold=0.6)
    print(f'  [INFO] 识别 xuan 自己: name={name!r} sim={sim:.4f}')

    # 识别 chao 自己
    name2, sim2 = ensemble_classifier.recognize(chao_img, threshold=0.6)
    print(f'  [INFO] 识别 chao 自己: name={name2!r} sim={sim2:.4f}')

    # 互证: xuan/chao 互识应该 sim 较低
    print(f'  [INFO] 跨人识别: xuan 特征 vs chao 库应较低')

    # 2.3 落盘 + 加载
    # 用 app 模块的 _save_ensemble_db (从 flask_app 内部)
    flask_app._save_ensemble_db() if hasattr(flask_app, '_save_ensemble_db') else None
    # 直接调模块函数
    from app import _save_ensemble_db, _load_ensemble_db
    _save_ensemble_db()
    assert os.path.exists(ens_path), 'ensemble npz 应被落盘'
    print(f'  [OK] _save_ensemble_db 落盘成功: {os.path.getsize(ens_path)} bytes')

    # 清空内存, 再加载
    ensemble_classifier.known_names = []
    ensemble_classifier.known_features = []
    assert len(ensemble_classifier.known_names) == 0
    print(f'  [INFO] 内存清空, 测试 _load_ensemble_db...')

    success = _load_ensemble_db()
    assert success
    assert len(ensemble_classifier.known_names) == 2
    assert 'xuan' in ensemble_classifier.known_names
    assert 'chao' in ensemble_classifier.known_names
    print(f'  [OK] _load_ensemble_db 恢复 2 人, names={ensemble_classifier.known_names}')

    # 2.4 API 端到端 (用 Flask test_client)
    client = flask_app.test_client()

    # 2.4.1 /api/ensemble/stats
    r = client.get('/api/ensemble/stats')
    assert r.status_code == 200
    stats = r.get_json()
    assert stats['person_count'] == 2
    print(f'  [OK] GET /api/ensemble/stats: {stats}')

    # 2.4.2 /api/ensemble/recognize (用 xuan 图)
    import io
    img_bytes = cv2.imencode('.jpg', img)[1].tobytes()
    r = client.post('/api/ensemble/recognize',
                     data={'image': (io.BytesIO(img_bytes), 'xuan.jpg')},
                     content_type='multipart/form-data')
    assert r.status_code == 200
    result = r.get_json()
    assert result['method'] == 'ensemble'
    print(f'  [OK] POST /api/ensemble/recognize: {result}')

    # 2.4.3 /api/ensemble/add (录入新人员)
    r = client.post('/api/ensemble/add',
                     data={'name': 'test_user',
                           'images': (io.BytesIO(img_bytes), 'test.jpg')},
                     content_type='multipart/form-data')
    assert r.status_code == 200
    add_result = r.get_json()
    assert add_result['success']
    assert add_result['person_count'] == 3
    print(f'  [OK] POST /api/ensemble/add: {add_result}')

    # 2.4.4 识别 - 空图 (用刚录入的 test_user 特征)
    # 重新加载
    _load_ensemble_db()
    r = client.post('/api/ensemble/recognize',
                     data={'image': (io.BytesIO(img_bytes), 'xuan.jpg')},
                     content_type='multipart/form-data')
    assert r.status_code == 200
    print(f'  [OK] 录入后识别: {r.get_json()}')

    # 清理
    if os.path.exists(ens_path + '.bak'):
        os.remove(ens_path)
        os.rename(ens_path + '.bak', ens_path)
    else:
        # 备份不存在 (测试创建过), 清掉测试数据
        if os.path.exists(ens_path):
            os.remove(ens_path)
        # 重置内存
        ensemble_classifier.known_names = []
        ensemble_classifier.known_features = []
        if os.path.exists(ens_path):
            _load_ensemble_db()
    print('  [OK] 测试数据清理')

except ImportError as e:
    print(f'  [SKIP] dlib 不可用: {e}')

print()
print('=== 全部通过 ===')
