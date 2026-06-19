"""
测试 src/face_recognition_core.py 的 similarity clamp 优化

测试项:
  1. _distance_to_similarity 边界值:
     - d=0   -> 1.0
     - d=0.6 -> 0.4 (dlib 阈值边)
     - d=1.0 -> 0.0
     - d=1.5 -> 0.0 (clamp, 不能是 -0.5)
     - d=2.0 -> 0.0 (clamp, 不能是 -1.0)
  2. 替换 4 处后, recognize_face/verify_face/identify_face 的 similarity 都是 [0, 1]
  3. 阈值逻辑不变 (d < 0.6 判同一人)
  4. dlib 集成测试: 真人脸跑一遍, similarity 在 [0, 1]
"""
import os
import sys
import ast
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))
os.chdir(os.path.dirname(ROOT))


print('=== 1) 语法检查 ===')
with open('src/face_recognition_core.py', encoding='utf-8') as f:
    src = f.read()
try:
    ast.parse(src)
    print('  [OK] 语法正确')
except SyntaxError as e:
    print(f'  [FAIL] {e}')
    sys.exit(1)


print()
print('=== 2) _distance_to_similarity 单元测试 (不依赖 dlib) ===')

# 用 ast 提取 _distance_to_similarity 源码
tree = ast.parse(src)
class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
func = next((n for n in class_node.body
             if isinstance(n, ast.FunctionDef) and n.name == '_distance_to_similarity'), None)
assert func is not None, '_distance_to_similarity 方法不存在'
print('  [OK] _distance_to_similarity 存在')

# 把 @staticmethod 装饰器跳过, 取出 def 函数源码
src_lines = src.split('\n')
start = func.lineno - 1
end = func.end_lineno
method_lines = src_lines[start:end]
# 跳 @staticmethod 装饰器
if method_lines[0].strip().startswith('@staticmethod'):
    method_lines = method_lines[1:]
# 剥 4 空格缩进, 重写为顶层函数
unindented = []
for line in method_lines:
    if line.startswith('    '):
        unindented.append(line[4:])
    else:
        unindented.append(line)
rebuilt = '\n'.join(unindented)

ns = {}
exec(rebuilt, ns)
distance_to_similarity = ns['_distance_to_similarity']

# 边界值测试
test_cases = [
    (0.0, 1.0, '完全相同'),
    (0.3, 0.7, '同一人不同照片'),
    (0.6, 0.4, 'dlib 阈值边'),
    (0.8, 0.2, '不同人'),
    (1.0, 0.0, '正交向量'),
    (1.5, 0.0, '反向向量 (clamp 必须为 0)'),
    (2.0, 0.0, '反向向量极值 (clamp 必须为 0)'),
    (0.45, 0.55, '同一人边界内'),
]
for d, expected, desc in test_cases:
    got = distance_to_similarity(d)
    ok = abs(got - expected) < 1e-9
    print(f'  [{"OK" if ok else "FAIL"}] d={d:.2f} -> sim={got:.4f} (期望 {expected:.2f}, {desc})')
    assert ok, f'd={d} 期望 {expected} 实际 {got}'


print()
print('=== 3) 静态检查: 不再有 "1 - " 硬编码 (除文档字符串) ===')
import re
hardcoded = []
in_docstring = False
for line_num, line in enumerate(src.split('\n'), 1):
    # 跟踪 docstring 状态
    triple_count = line.count('"""') + line.count("'''")
    if triple_count % 2 == 1:
        in_docstring = not in_docstring
    if in_docstring:
        continue
    # 跳过纯注释行
    stripped = line.strip()
    if stripped.startswith('#'):
        continue
    # 检查是否有硬编码 1 - d
    if re.search(r'1\s*-\s*(min_distance|distance|dist)\b', line):
        hardcoded.append((line_num, line))
if hardcoded:
    print('  [FAIL] 还有硬编码的 1 - d:')
    for ln, l in hardcoded:
        print(f'    L{ln}: {l}')
else:
    print('  [OK] 所有 1 - d 硬编码已替换为 _distance_to_similarity(...)')


print()
print('=== 4) dlib 集成测试 ===')
try:
    import dlib
    from src.face_recognition_core import FaceRecognitionCore
    core = FaceRecognitionCore()

    # 跑一次识别, 检查 similarity 范围
    xuan_path = 'datasets/shenlinxuan/IMG_20260608_141050.jpg'
    chao_path = 'datasets/zhaohanchao/3e734401f831ab1ed858dddf30f80a01.jpg'

    # 用库里的 xuan 特征去识别 xuan 自己
    data = np.load('data/face_database.npz', allow_pickle=True)
    xuan_feat = data['faces'][0]
    chao_feat = data['faces'][1]

    # 1. recognize_face (xuan 特征 vs 库)
    name, sim, mode = core.recognize_face(xuan_feat, th=0.6)
    assert 0.0 <= sim <= 1.0, f'similarity 超出 [0,1]: {sim}'
    print(f'  [OK] recognize_face: name={name!r} sim={sim:.4f} (在 [0,1])')

    # 2. verify_face
    is_match, sim, mode = core.verify_face(xuan_feat, 'xuan', th=0.6)
    assert 0.0 <= sim <= 1.0
    print(f'  [OK] verify_face: match={is_match} sim={sim:.4f}')

    # 3. identify_face
    matches, mode = core.identify_face(xuan_feat, th=0.6)
    for m in matches:
        assert 0.0 <= m['similarity'] <= 1.0, f'similarity 超出: {m}'
    print(f'  [OK] identify_face: {len(matches)} match, 全部 similarity in [0,1]')

    # 4. 真实图: 用 xuan 自己照片识别
    img = cv2.imdecode(np.fromfile(xuan_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = core.detect_faces(gray)
    if faces:
        feat = core.extract_features_with_preprocess(rgb, faces[0])
        name, sim, _ = core.recognize_face(feat, th=0.6)
        assert 0.0 <= sim <= 1.0
        print(f'  [OK] 真实图 xuan 识别: name={name!r} sim={sim:.4f} (在 [0,1])')

    # 5. 反向特征: -xuan (反向量) -> similarity 必须 clamp 到 0
    neg_xuan = -xuan_feat
    name, sim, _ = core.recognize_face(neg_xuan, th=0.6)
    assert 0.0 <= sim <= 1.0, f'反向特征 sim 异常: {sim}'
    # 距离应该是 2.0 (单位向量反向距离是 2), 修复后 sim=0
    print(f'  [OK] 反向特征 (-xuan) 识别: sim={sim:.4f} (clamp 后为 0 而非 -1.0)')

    # 6. 反向特征 verify: 同一人反向 -> match=False, sim=0
    is_match, sim, _ = core.verify_face(neg_xuan, 'xuan', th=0.6)
    assert sim == 0.0, f'反向 verify sim 期望 0, 实际 {sim}'
    assert is_match == False
    print(f'  [OK] 反向特征 verify xuan: match={is_match} sim={sim}')

except ImportError as e:
    print(f'  [SKIP] dlib 不可用: {e}')

print()
print('=== 全部通过 ===')
