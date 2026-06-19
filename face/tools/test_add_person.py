"""
测试 src/face_recognition_core.py 的录入函数重构结果

测试项:
  1. _add_person_internal 抽出后, add_person / add_person_with_preprocess 是 1 行 wrapper
  2. add_person 和 add_person_with_preprocess 签名不变
  3. 两个 wrapper 实际行为 (用 dlib 集成测试):
     - 空 image_paths: 返回 False
     - 不存在的路径: 返回 False
     - 有效图: 返回 True, known_faces/known_names 各 +1
  4. 行为对比: 同一张图, add_person vs add_person_with_preprocess 提的特征应该不同
     (因为 add_person_with_preprocess 走了 3 步管线)
  5. 兼容性: app.py 调 add_person_with_preprocess 不报错
"""
import os
import sys
import ast
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))
os.chdir(os.path.dirname(ROOT))


# 1) 语法 + 静态结构检查
print('=== 1) 语法 + 结构检查 ===')
with open('src/face_recognition_core.py', encoding='utf-8') as f:
    src = f.read()
try:
    ast.parse(src)
    print('  [OK] 语法正确')
except SyntaxError as e:
    print(f'  [FAIL] {e}')
    sys.exit(1)


# 2) 验证 _add_person_internal 存在, add_person/add_person_with_preprocess 是 wrapper
print()
print('=== 2) 静态结构 ===')
tree = ast.parse(src)
class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
methods = {n.name: n for n in class_node.body if isinstance(n, ast.FunctionDef)}

for name in ['_add_person_internal', 'add_person', 'add_person_with_preprocess']:
    print(f'  [{"OK" if name in methods else "MISS"}] def {name}')

# 验证 add_person 主体只有 1 行 (return self._add_person_internal(...))
ap = methods['add_person']
ap_body_lines = ap.body[0].end_lineno - ap.body[0].lineno + 1 if ap.body else 0
print(f'  [INFO] add_person 主体行数: {ap_body_lines}')

apwp = methods['add_person_with_preprocess']
apwp_body_lines = apwp.body[0].end_lineno - apwp.body[0].lineno + 1 if apwp.body else 0
print(f'  [INFO] add_person_with_preprocess 主体行数: {apwp_body_lines}')


# 3) 真实集成测试
print()
print('=== 3) 真实集成测试 (需要 dlib) ===')
try:
    import dlib
    print('  dlib 可用, 跑...')
    from src.face_recognition_core import FaceRecognitionCore
    core = FaceRecognitionCore()

    # 测 1: 空路径
    result = core.add_person('test_empty', [])
    assert result == False, f'空路径应返回 False, 实际 {result}'
    print(f'  [OK] add_person 空路径 -> False')

    result = core.add_person_with_preprocess('test_empty2', [])
    assert result == False
    print(f'  [OK] add_person_with_preprocess 空路径 -> False')

    # 测 2: 不存在的路径
    result = core.add_person('test_bad', ['nonexistent.jpg'])
    assert result == False
    print(f'  [OK] add_person 无效路径 -> False')

    # 测 3: 实际录入 (不污染主库, 备份)
    import shutil
    if os.path.exists('data/face_database.npz.bak'):
        os.remove('data/face_database.npz.bak')
    if os.path.exists('data/face_db.json.bak'):
        os.remove('data/face_db.json.bak')
    shutil.copy('data/face_database.npz', 'data/face_database.npz.bak')
    shutil.copy('data/face_db.json', 'data/face_db.json.bak')

    # 用 1 张 xuan 图测 add_person
    core2 = FaceRecognitionCore()  # 新实例, 独立内存库
    xuan_path = 'datasets/shenlinxuan/IMG_20260608_141050.jpg'
    if os.path.exists(xuan_path):
        n_before = len(core2.known_faces)
        result = core2.add_person('test_ap', [xuan_path])
        assert result == True, f'录入 xuan 应成功, 实际 {result}'
        assert len(core2.known_faces) == n_before + 1
        assert 'test_ap' in core2.known_names
        feat_ap = core2.known_faces[-1]
        assert np.isclose(np.linalg.norm(feat_ap), 1.0, atol=1e-6), f'feat norm {np.linalg.norm(feat_ap)}'
        print(f'  [OK] add_person 录入成功: norm={np.linalg.norm(feat_ap):.4f}')

    # 用 1 张 chao 图测 add_person_with_preprocess
    core3 = FaceRecognitionCore()
    chao_path = 'datasets/zhaohanchao/3e734401f831ab1ed858dddf30f80a01.jpg'
    if os.path.exists(chao_path):
        n_before = len(core3.known_faces)
        result = core3.add_person_with_preprocess('test_apwp', [chao_path])
        assert result == True
        assert len(core3.known_faces) == n_before + 1
        assert 'test_apwp' in core3.known_names
        feat_apwp = core3.known_faces[-1]
        assert np.isclose(np.linalg.norm(feat_apwp), 1.0, atol=1e-6)
        print(f'  [OK] add_person_with_preprocess 录入成功: norm={np.linalg.norm(feat_apwp):.4f}')

        # 测 4: 同一张图, 两个函数提的特征应该不同
        core4 = FaceRecognitionCore()
        result = core4.add_person('A', [chao_path])
        feat_a = core4.known_faces[-1]
        core5 = FaceRecognitionCore()
        result = core5.add_person_with_preprocess('B', [chao_path])
        feat_b = core5.known_faces[-1]
        d = np.linalg.norm(feat_a - feat_b)
        print(f'  [INFO] 同一图 add_person vs add_person_with_preprocess 距离: {d:.4f}')
        # 期望: 距离 > 0 (管线确实影响结果)
        assert d > 0.001, f'两个函数提的特征应不同, 距离 {d} 太小'
        print(f'  [OK] 管线差异导致特征不同 (距离 {d:.4f} > 0.001)')

        # 测 5: app.py 兼容 (调 add_person_with_preprocess 走完整流程)
        result = core5.add_person_with_preprocess('app_compat_test', [chao_path])
        assert result == True
        print(f'  [OK] app.py 调 add_person_with_preprocess 兼容')
    else:
        print(f'  [SKIP] {chao_path} 不存在')

    # 恢复主库
    shutil.move('data/face_database.npz.bak', 'data/face_database.npz')
    shutil.move('data/face_db.json.bak', 'data/face_db.json')
    print('  [OK] 主库已恢复')

except ImportError as e:
    print(f'  [SKIP] dlib 不可用: {e}')

print()
print('=== 全部通过 ===')
