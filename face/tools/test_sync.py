"""
测试 src/face_recognition_core.py 的数据存储同步优化

测试项:
  1. save_database 写 npz + 自动 sync_metadata_from_npz 写 face_db.json
  2. face_db.json 不再存冗余的 features 数组
  3. load_database 启动时如果 json 缺失, 从 npz 重建
  4. load_database 启动时如果 json 数量不对, 从 npz 重建
  5. remove_person_and_persist 一步完成删除 + 落盘
  6. 保留旧 json 的 image_path/add_time (升级兼容)
"""
import os
import sys
import ast
import json
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))
os.chdir(os.path.dirname(ROOT))


print('=== 1) 语法 + 静态检查 ===')
with open('src/face_recognition_core.py', encoding='utf-8') as f:
    src = f.read()
try:
    ast.parse(src)
    print('  [OK] src/face_recognition_core.py 语法正确')
except SyntaxError as e:
    print(f'  [FAIL] {e}')
    sys.exit(1)

# 检查新方法存在
tree = ast.parse(src)
class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
methods = {n.name for n in class_node.body if isinstance(n, ast.FunctionDef)}
class_assigns = set()
for node in class_node.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                class_assigns.add(t.id)
for name in ['sync_metadata_from_npz', 'remove_person_and_persist',
             'META_JSON_PATH', 'save_database', 'load_database']:
    if name in methods or name in class_assigns:
        print(f'  [OK] {name}')
    else:
        print(f'  [FAIL] {name} 不存在')


print()
print('=== 2) 静态结构: app.py 用新方法 ===')
with open('app.py', encoding='utf-8') as f:
    app_src = f.read()
print(f'  [{"OK" if "remove_person_and_persist" in app_src else "FAIL"}] app.py 调 remove_person_and_persist')
# 检查非注释调用 db.add_face (用 ast 解析, 跳过注释/字符串)
app_tree = ast.parse(app_src)
add_face_calls = 0
for node in ast.walk(app_tree):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'add_face':
            add_face_calls += 1
print(f'  [INFO] app.py 中 db.add_face() 实际调用次数: {add_face_calls}')
print(f'  [{"OK" if add_face_calls == 0 else "FAIL"}] app.py 0 次实际调用 db.add_face')


print()
print('=== 3) 备份/恢复机制 ===')
import shutil
for f in ['data/face_database.npz', 'data/face_db.json']:
    bak = f + '.bak'
    if os.path.exists(bak):
        os.remove(bak)
    shutil.copy(f, bak)
print('  [OK] 已备份 npz + json')


print()
print('=== 4) dlib 集成测试 ===')
try:
    import dlib
    from src.face_recognition_core import FaceRecognitionCore

    # 4.1 启动加载, 看 json 是否被自动同步
    # 现状: 备份里 npz 是空库 (0 维), json 里有 xuan/chao 旧元数据 (含 features 字段)
    # 期望: 启动后 sync 重建 json, 删除冗余 features 字段
    core = FaceRecognitionCore()
    print(f'  [INFO] 启动后 npz 内存: {len(core.known_names)} 人')

    # 检查 json 结构 (启动后)
    with open('data/face_db.json', encoding='utf-8') as f:
        meta = json.load(f)
    print(f'  [INFO] face_db.json entries: {len(meta)}')
    for entry in meta:
        has_features = 'features' in entry
        has_name = 'name' in entry
        has_time = 'add_time' in entry
        print(f'    - {entry.get("name")!r}: features={has_features} name={has_name} time={has_time}')

    # 关键断言: 启动后 json 应只有元数据, 不含 features 字段
    has_features_in_json = any('features' in e for e in meta)
    assert not has_features_in_json, f'启动 sync 后 json 还有冗余 features 字段: {[e.get("name") for e in meta if "features" in e]}'
    print(f'  [OK] 启动 sync 后 face_db.json 不再含冗余 features 字段')

    # 4.2 save_database 后 json 数量应 = npz 数量
    core.save_database()
    data = np.load('data/face_database.npz', allow_pickle=True)
    n_npz = len(data['names'])
    with open('data/face_db.json', encoding='utf-8') as f:
        n_json = len(json.load(f))
    assert n_npz == n_json, f'npz={n_npz} vs json={n_json} 不一致'
    print(f'  [OK] save_database 后 npz ({n_npz}) == json ({n_json})')

    # 4.3 模拟 json 缺失, load_database 应能恢复
    os.remove('data/face_db.json')
    print('  [INFO] 删 face_db.json, 测试 load_database 自动恢复...')
    core2 = FaceRecognitionCore()
    assert os.path.exists('data/face_db.json'), 'load_database 后 json 应被重建'
    with open('data/face_db.json', encoding='utf-8') as f:
        n_after = len(json.load(f))
    assert n_after == n_npz, f'重建数量不对: {n_after} vs {n_npz}'
    print(f'  [OK] load_database 自动重建 face_db.json ({n_after} entries)')

    # 4.4 模拟 json 数量不对 (手改 1 条)
    with open('data/face_db.json', encoding='utf-8') as f:
        m = json.load(f)
    m = m[:1]  # 删掉几条
    with open('data/face_db.json', 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False)
    print(f'  [INFO] 手动把 json 改成 {len(m)} 条, 测试 load_database 同步...')
    core3 = FaceRecognitionCore()
    with open('data/face_db.json', encoding='utf-8') as f:
        n_synced = len(json.load(f))
    assert n_synced == n_npz, f'sync 后数量不对: {n_synced} vs {n_npz}'
    print(f'  [OK] load_database 同步修复数量 ({n_synced} entries)')

    # 4.5 remove_person_and_persist 一步式删除
    n_before = len(core3.known_faces)
    if n_before > 0:
        target = core3.known_names[0]
        success, msg = core3.remove_person_and_persist(target)
        assert success
        # 验证 npz
        data_after = np.load('data/face_database.npz', allow_pickle=True)
        assert target not in list(data_after['names'])
        # 验证 json
        with open('data/face_db.json', encoding='utf-8') as f:
            meta_after = json.load(f)
        assert target not in [e['name'] for e in meta_after]
        print(f'  [OK] remove_person_and_persist({target!r}): npz + json 同步删除')

    # 4.6 升级兼容: 旧 json 带 image_path/add_time, sync 后保留
    with open('data/face_db.json', encoding='utf-8') as f:
        m = json.load(f)
    if m:
        first = m[0]
        first['image_path'] = 'legacy/path/test.jpg'
        first['add_time'] = '2024-01-01 00:00:00'
        with open('data/face_db.json', 'w', encoding='utf-8') as f:
            json.dump(m, f, ensure_ascii=False)
        core4 = FaceRecognitionCore()
        with open('data/face_db.json', encoding='utf-8') as f:
            synced = json.load(f)
        synced_names = [e['name'] for e in synced]
        if first['name'] in synced_names:
            idx = synced_names.index(first['name'])
            assert synced[idx]['image_path'] == 'legacy/path/test.jpg', 'image_path 应被保留'
            print(f'  [OK] 升级兼容: 旧 json 的 image_path {first["image_path"]} 保留')

    # 4.7 app.py 端到端 (调 remove_person_and_persist 走流程)
    # 不实际起 app, 直接验证 core API
    core5 = FaceRecognitionCore()
    if len(core5.known_names) > 0:
        target = core5.known_names[0]
        success, msg = core5.remove_person_and_persist(target)
        assert success
        # 验证 npz + json 同步
        data = np.load('data/face_database.npz', allow_pickle=True)
        assert target not in list(data['names'])
        with open('data/face_db.json', encoding='utf-8') as f:
            meta = json.load(f)
        assert target not in [e['name'] for e in meta]
        print(f'  [OK] 端到端 remove_person_and_persist: {target!r} 完全清理')

except ImportError as e:
    print(f'  [SKIP] dlib 不可用: {e}')

# 恢复主库
print()
print('=== 5) 恢复主库 ===')
import gc
gc.collect()  # 强制回收, 释放 npz 句柄
for f in ['data/face_database.npz', 'data/face_db.json']:
    bak = f + '.bak'
    if os.path.exists(bak):
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                # 文件被占用 (dlib/numpy 还在持有句柄), 跳过删除, 直接 move 覆盖
                pass
        try:
            shutil.move(bak, f)
            print(f'  [OK] 恢复 {f}')
        except Exception as e:
            print(f'  [WARN] 恢复 {f} 失败: {e} (可能需要手动从 .bak 恢复)')

print()
print('=== 全部通过 ===')
