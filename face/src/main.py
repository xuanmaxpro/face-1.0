"""
项目启动入口
Web 端人脸识别系统 — Flask 后端

启动方法:
    python src/main.py
    或 (在项目根目录): python -m src.main
启动后访问: http://localhost:5000
"""

import os
import sys

# 把项目根目录加入 sys.path,方便导入 src 包
# 这样无论从哪里运行这个脚本,都能找到 src/face_recognition_core.py 等模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """启动 Flask Web 服务"""
    # 延迟导入:避免模块加载阶段就尝试连数据库 / 加载模型,加快启动反馈
    from app import app

    print("=" * 50)
    print("人脸识别系统 - Web 服务启动")
    print("访问地址: http://localhost:5000")
    print("=" * 50)
    # host='0.0.0.0' — 监听所有网卡,局域网内可访问 (不只是 127.0.0.1)
    # port=5000 — Flask 默认端口
    # debug=True — 改代码自动重载,方便开发 (生产用 gunicorn 等 WSGI 服务器)
    app.run(host='0.0.0.0', port=5000, debug=True)


if __name__ == '__main__':
    main()
