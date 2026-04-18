from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
import os
import uuid
import socket
from datetime import datetime
import threading
import time
import json
import logging
import base64

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 历史记录文件路径
HISTORY_FILE = 'message_history.json'

app = Flask(__name__)
CORS(app)

# 创建文件存储目录
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 不限大小
app.config['MAX_CONTENT_LENGTH'] = None

# 存储在线用户
online_users = {}
# 存储消息历史
message_history = []
# 存储最近发送的消息（用于防重复）
recent_messages = {}  # {sender_ip: {last_message: str, timestamp: float}}
MIN_MESSAGE_INTERVAL = 1  # 最小消息间隔（秒）

# 从文件加载历史消息
def load_message_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"加载历史消息失败: {str(e)}")
    return []

# 保存消息历史到文件
def save_message_history(messages):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存历史消息失败: {str(e)}")

# 初始化加载历史消息
message_history = load_message_history()
# 存储传输中的文件信息
active_transfers = {}
# 消息通知的回调函数列表
message_callbacks = []
# 线程锁
lock = threading.RLock()

# 获取本机IP地址
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 连接到外部地址以获取本机IP
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# 首页 - 提供前端界面
@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="theme-color" content="#667eea">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <title>浅月不息 - 局域网互传</title>
        <style>
            /* 基础样式重置 */
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                -webkit-tap-highlight-color: transparent;
            }
            
            /* 根样式 */
            :root {
                --primary-color: #667eea;
                --secondary-color: #764ba2;
                --bg-color: #f5f5f5;
                --card-bg: #ffffff;
                --text-primary: #333333;
                --text-secondary: #666666;
                --border-color: #e9ecef;
                --success-color: #2ecc71;
                --shadow-sm: 0 2px 4px rgba(0,0,0,0.1);
                --shadow-md: 0 4px 8px rgba(0,0,0,0.15);
                --border-radius: 12px;
            }
            
            /* 基础布局 */
            body {
                background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
                min-height: 100vh;
                color: var(--text-primary);
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
                position: relative;
                margin: 0;
                overflow-x: hidden;
            }
            
            /* 加载动画 */
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            /* 加载页面淡入淡出效果 */
            .fade-out {
                opacity: 0 !important;
                pointer-events: none;
            }
            
            .container {
                background: var(--card-bg);
                border-radius: var(--border-radius);
                box-shadow: var(--shadow-md);
                max-width: 1200px;
                width: 100%;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                height: 90vh;
            }
            
            /* 头部样式 */
            .header {
                background: linear-gradient(90deg, var(--primary-color) 0%, var(--secondary-color) 100%);
                color: white;
                padding: 20px;
                text-align: center;
                box-shadow: var(--shadow-sm);
                position: relative;
                z-index: 10;
            }
            
            .header h1 {
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }
            
            .header p {
                margin: 10px 0 0;
                font-size: 14px;
                opacity: 0.9;
            }
            
            /* 主内容区 */
            .content {
                display: flex;
                flex: 1;
                overflow: hidden;
            }
            
            /* 侧边栏 */
            .sidebar {
                width: 300px;
                background: #f8f9fa;
                border-right: 1px solid var(--border-color);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            
            /* 聊天区域 */
            .chat-area {
                flex: 1;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            
            /* 昵称显示区域 */
            .nickname-display {
                margin: 15px;
                padding: 15px;
                background: var(--card-bg);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            
            .nickname-display span {
                font-size: 14px;
                color: var(--text-color-secondary);
            }
            
            #nicknameInput {
                padding: 8px 12px;
                border: 1px solid var(--primary-color);
                border-radius: 4px;
                background: var(--background-color);
                color: var(--text-color);
                font-size: 14px;
                outline: none;
                transition: border-color 0.3s;
            }
            
            #nicknameInput:focus {
                border-color: var(--primary-color-dark);
            }
            
            #saveNickname {
                padding: 8px 16px;
                background: var(--primary-color);
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                transition: background-color 0.3s;
            }
            
            #saveNickname:hover {
                background: var(--primary-color-dark);
            }
            
            /* 用户信息 */
            .user-info {
                padding: 20px;
                border-bottom: 1px solid var(--border-color);
                background: var(--card-bg);
            }
            
            .user-info h3 {
                margin: 0 0 10px;
                font-size: 16px;
                color: var(--primary-color);
            }
            
            .user-info p {
                font-size: 14px;
                color: var(--text-secondary);
                margin: 5px 0;
                word-break: break-all;
            }
            
            .online-users {
                padding: 15px;
                border-bottom: 1px solid #e9ecef;
            }
            
            .online-users h4 {
                font-size: 14px;
                color: #666;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
            }
            
            .online-users h4 .dot {
                width: 8px;
                height: 8px;
                background: #28a745;
                border-radius: 50%;
                margin-right: 8px;
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }
            
            .user-list {
                list-style: none;
                overflow-y: auto;
                flex: 1;
                padding: 10px;
            }
            
            .user-list li {
                padding: 10px 15px;
                margin-bottom: 5px;
                border-radius: 8px;
                background: white;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                transition: all 0.3s ease;
                cursor: pointer;
            }
            
            .user-list li:hover {
                    background: #667eea;
                    color: white;
                    transform: translateX(5px);
                }
                
                /* 历史管理区域样式 */
                .history-management {
                    padding: 15px;
                    border-top: 1px solid var(--border-color);
                    background: var(--card-bg);
                }
                
                .history-management h4 {
                    font-size: 14px;
                    color: #666;
                    margin-bottom: 10px;
                }
                
                .history-controls {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                }
                
                .btn-small {
                    padding: 6px 12px;
                    font-size: 12px;
                    border-radius: 16px;
                }
                
                /* 右键菜单样式 */
                .context-menu {
                    position: fixed;
                    background: white;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 4px 0;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                    z-index: 1000;
                    display: none;
                }
                
                .context-menu-item {
                    padding: 8px 16px;
                    cursor: pointer;
                    font-size: 14px;
                }
                
                .context-menu-item:hover {
                    background: #f0f0f0;
                }
            
            .user-list li .user-name {
                font-weight: 500;
                margin-bottom: 3px;
            }
            
            .user-list li .user-ip {
                font-size: 12px;
                opacity: 0.7;
            }
            
            .messages {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                background: #f5f7fa;
            }
            
            .message {
                margin-bottom: 15px;
                display: flex;
                flex-direction: column;
            }
            
            .message.own {
                align-items: flex-end;
            }
            
            .message.other {
                align-items: flex-start;
            }
            
            .message-header {
                font-size: 12px;
                color: #666;
                margin-bottom: 5px;
            }
            
            /* 一对一传输标签样式 */
            .direct-transfer-label {
                color: #007bff;
                font-size: 10px;
                font-weight: 500;
                padding: 2px 8px;
                background-color: #e3f2fd;
                border-radius: 10px;
            }
            
            .message-content {
                max-width: 70%;
                padding: 12px 16px;
                border-radius: 18px;
                word-wrap: break-word;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            
            .message.own .message-content {
                background: #667eea;
                color: white;
                border-bottom-right-radius: 4px;
            }
            
            .message.other .message-content {
                background: white;
                color: #333;
                border-bottom-left-radius: 4px;
            }
            
            .file-message {
                background: white;
                border-radius: 12px;
                padding: 15px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                max-width: 400px;
                width: 100%;
            }
            
            .file-info {
                display: flex;
                align-items: center;
                margin-bottom: 10px;
            }
            
            .file-icon {
                font-size: 24px;
                margin-right: 12px;
                color: #667eea;
            }
            
            .file-details {
                flex: 1;
            }
            
            .file-name {
                font-weight: 500;
                margin-bottom: 3px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            
            .file-size {
                font-size: 12px;
                color: #666;
            }
            
            .file-progress {
                width: 100%;
                height: 6px;
                background: #e9ecef;
                border-radius: 3px;
                overflow: hidden;
                margin-bottom: 8px;
            }
            
            .file-progress-bar {
                height: 100%;
                background: linear-gradient(90deg, #667eea, #764ba2);
                border-radius: 3px;
                transition: width 0.3s ease;
            }
            
            .file-actions {
                display: flex;
                justify-content: flex-end;
                gap: 10px;
            }
            
            .btn {
                padding: 8px 16px;
                border: none;
                border-radius: 20px;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-weight: 500;
            }
            
            .btn-primary {
                background: #667eea;
                color: white;
            }
            
            .btn-primary:hover {
                background: #5a67d8;
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(102, 126, 234, 0.3);
            }
            
            .btn-secondary {
                background: #e9ecef;
                color: #495057;
            }
            
            .btn-secondary:hover {
                background: #dee2e6;
                transform: translateY(-1px);
            }
            
            .input-area {
                padding: 20px;
                background: white;
                border-top: 1px solid #e9ecef;
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            
            .text-input-container {
                display: flex;
                gap: 10px;
                align-items: flex-end;
            }
            
            #messageInput {
                flex: 1;
                padding: 12px 16px;
                border: 2px solid #e9ecef;
                border-radius: 25px;
                font-size: 16px;
                outline: none;
                transition: border-color 0.3s ease;
                resize: none;
                max-height: 120px;
                min-height: 45px;
            }
            
            #messageInput:focus {
                border-color: #667eea;
            }
            
            .upload-area {
                border: 2px dashed #e9ecef;
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                background: #f8f9fa;
            }
            
            .upload-area:hover {
                border-color: #667eea;
                background: #f0f2ff;
            }
            
            .upload-area.active {
                border-color: #667eea;
                background: #f0f2ff;
            }
            
            .upload-icon {
                font-size: 40px;
                color: #667eea;
                margin-bottom: 10px;
            }
            
            .upload-text {
                font-size: 16px;
                color: #666;
            }
            
            .upload-hint {
                font-size: 12px;
                color: #999;
                margin-top: 5px;
            }
            
            #fileInput {
                display: none;
            }
            
            .transfers-section {
                margin-top: 20px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 12px;
            }
            
            .transfers-section h4 {
                font-size: 14px;
                color: #666;
                margin-bottom: 10px;
            }
            
            .transfer-item {
                background: white;
                padding: 10px;
                border-radius: 8px;
                margin-bottom: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            
            .transfer-info {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 5px;
                font-size: 14px;
            }
            
            .transfer-progress {
                width: 100%;
                height: 4px;
                background: #e9ecef;
                border-radius: 2px;
                overflow: hidden;
            }
            
            .transfer-progress-bar {
                height: 100%;
                background: linear-gradient(90deg, #667eea, #764ba2);
                border-radius: 2px;
                transition: width 0.3s ease;
            }
            
            .transfer-speed {
                font-size: 12px;
                color: #666;
                text-align: right;
                margin-top: 3px;
            }
            
            @media (max-width: 768px) {
                /* 基础样式调整 */
                body {
                    padding: 0;
                    margin: 0;
                    font-size: 16px;
                    background-color: #f8f9fa;
                }
                
                .container {
                    height: 100vh;
                    border-radius: 0;
                    box-shadow: none;
                    border: none;
                }
                
                .header {
                    padding: 12px 16px;
                    background-color: var(--primary-color);
                    color: white;
                }
                
                .header h1 {
                    font-size: 18px;
                    margin: 0;
                    font-weight: 600;
                }
                
                .header p {
                    display: none; /* 在移动端隐藏副标题 */
                }
                
                /* 内容区域 - 移动端优先布局 */
                .content {
                    flex-direction: column;
                    height: calc(100vh - 60px); /* 减去头部高度 */
                }
                
                /* 侧边栏 - 可折叠设计 */
                /* 在移动端隐藏原侧边栏 */
                .sidebar {
                    display: none;
                }
                
                /* 显示菜单按钮 */
                .menu-toggle {
                    display: block !important;
                    padding: 8px 16px;
                    font-size: 14px;
                }
                
                .sidebar.active {
                    height: 200px;
                }
                
                .user-info {
                    padding: 12px 16px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    cursor: pointer;
                }
                
                .user-info h3 {
                    font-size: 14px;
                    margin: 0;
                }
                
                .user-info p {
                    font-size: 12px;
                    margin: 0;
                    color: #666;
                }
                
                .user-info::after {
                    content: '▼';
                    font-size: 12px;
                    transition: transform 0.3s ease;
                }
                
                .sidebar.active .user-info::after {
                    transform: rotate(180deg);
                }
                
                .online-users {
                    padding: 0 16px 16px;
                }
                
                .online-users h4 {
                    font-size: 14px;
                    margin: 0 0 10px 0;
                }
                
                .user-list {
                    margin: 0;
                    padding: 0;
                    list-style: none;
                    max-height: 120px;
                    overflow-y: auto;
                }
                
                .user-list li {
                    padding: 6px 0;
                    border-bottom: 1px solid #f0f0f0;
                }
                
                .user-name {
                    font-size: 14px;
                    font-weight: 500;
                }
                
                .user-ip {
                    font-size: 12px;
                    color: #666;
                }
                
                /* 聊天区域 */
                .chat-area {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                }
                
                .messages {
                    flex: 1;
                    padding: 12px 16px;
                    overflow-y: auto;
                }
                
                .message {
                    margin-bottom: 12px;
                }
                
                .message-header {
                    font-size: 11px;
                    margin-bottom: 4px;
                }
                
                .message-content {
                    max-width: 85%;
                    font-size: 16px;
                    padding: 12px 14px;
                    border-radius: 12px;
                }
                
                .message.own .message-content {
                    border-bottom-right-radius: 4px;
                }
                
                .message.other .message-content {
                    border-bottom-left-radius: 4px;
                }
                
                /* 文件消息 */
                .file-message {
                    max-width: 95%;
                    padding: 12px;
                }
                
                .file-info {
                    display: flex;
                    align-items: center;
                }
                
                .file-icon {
                    font-size: 24px;
                    margin-right: 12px;
                }
                
                .file-name {
                    font-size: 15px;
                    font-weight: 500;
                }
                
                .file-size {
                    font-size: 12px;
                    color: #666;
                }
                
                .file-actions button {
                    width: 100%;
                    padding: 8px;
                    font-size: 14px;
                }
                
                /* 输入区域 */
                .input-area {
                    padding: 12px 16px;
                    gap: 12px;
                    border-top: 1px solid #e9ecef;
                    background-color: white;
                }
                
                .upload-area {
                    padding: 16px;
                    margin-bottom: 8px;
                }
                
                .upload-icon {
                    font-size: 28px;
                }
                
                .upload-text {
                    font-size: 14px;
                    margin: 8px 0;
                }
                
                .upload-hint {
                    font-size: 12px;
                }
                
                .text-input-container {
                    display: flex;
                    gap: 8px;
                }
                
                #messageInput {
                    flex: 1;
                    font-size: 16px;
                    padding: 12px 16px;
                    min-height: 48px;
                    border-radius: 24px;
                    border: 1px solid #ddd;
                    resize: none;
                }
                
                .btn {
                    padding: 12px 20px;
                    font-size: 16px;
                    min-width: 70px;
                    border-radius: 24px;
                    background-color: var(--primary-color);
                    color: white;
                    border: none;
                }
                
                .btn-primary {
                    background-color: var(--primary-color);
                }
                
                /* 传输进度 */
                .transfers-section {
                    margin-top: 8px;
                }
                
                .transfers-section h4 {
                    font-size: 14px;
                    margin: 8px 0;
                }
                
                /* 连接状态样式 */
                .connection-status {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    padding: 10px;
                    text-align: center;
                    font-weight: bold;
                    z-index: 1000;
                    display: none;
                }
                
                .connection-status.connecting {
                    background-color: #ff9800;
                    color: white;
                    display: block;
                }
                
                .connection-status.connected {
                    background-color: #4caf50;
                    color: white;
                    display: block;
                }
                
                .connection-status.failed {
                    background-color: #f44336;
                    color: white;
                    display: block;
                }
                
                .transfer-item {
                    margin-bottom: 8px;
                }
                
                .transfer-info span {
                    font-size: 14px;
                }
                
                .transfer-speed {
                    font-size: 12px;
                }
                
                /* 添加可折叠侧边栏的JavaScript */
                document.querySelector('.user-info').addEventListener('click', function() {
                    document.querySelector('.sidebar').classList.toggle('active');
                });
            }
            
            @media (max-width: 480px) {
                /* 小屏手机特殊优化 */
                .sidebar.active {
                    height: 180px;
                }
                
                .user-list {
                    max-height: 100px;
                }
                
                .message-content {
                    max-width: 90%;
                    font-size: 15px;
                    padding: 10px 12px;
                }
                
                #messageInput {
                    font-size: 15px;
                    padding: 10px 14px;
                }
                
                .btn {
                    min-width: 60px;
                    padding: 10px 16px;
                    font-size: 15px;
                }
                
                /* 触控优化 */
                .upload-area, .btn, .file-actions button {
                    cursor: pointer;
                    touch-action: manipulation;
                    user-select: none;
                }
                
                /* 防止iOS上的双击缩放 */
                * {
                    touch-action: manipulation;
                }
                
                /* 增加点击区域大小，提高可用性 */
                .btn, .file-actions button {
                    min-height: 44px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                
                /* 优化输入区域在小屏幕上的显示 */
                .text-input-container {
                    gap: 6px;
                }
                
                /* 优化文件消息显示 */
                .file-message {
                    padding: 10px;
                }
                
                .file-icon {
                    font-size: 20px;
                    margin-right: 10px;
                }
            }
            /* 文件预览样式 */
            .file-preview {
                margin-bottom: 10px;
                border-radius: 8px;
                overflow: hidden;
                transition: transform 0.2s;
            }
            
            .file-preview:hover {
                transform: scale(1.01);
            }
            
            .file-preview-image img {
                max-width: 100%;
                max-height: 300px;
                object-fit: contain;
                border-radius: 8px;
                cursor: pointer;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            
            .file-preview-audio audio {
                width: 100%;
                max-width: 400px;
                background: #f8f9fa;
                border-radius: 8px;
                padding: 8px;
            }
            
            .file-preview-video video {
                width: 100%;
                max-width: 500px;
                max-height: 400px;
                border-radius: 8px;
                background: #000;
                box-shadow: 0 2px 12px rgba(0,0,0,0.15);
            }
            
            /* 全屏预览模态框 */
            .preview-modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.9);
                z-index: 1000;
                align-items: center;
                justify-content: center;
            }
            
            .preview-content {
                max-width: 90%;
                max-height: 90%;
                position: relative;
            }
            
            .preview-content img {
                max-width: 100%;
                max-height: 90vh;
                object-fit: contain;
            }
            
            .preview-content video {
                max-width: 100%;
                max-height: 90vh;
                object-fit: contain;
            }
            
            .preview-close {
                position: absolute;
                top: 20px;
                right: 30px;
                color: white;
                font-size: 40px;
                font-weight: bold;
                cursor: pointer;
                transition: 0.3s;
            }
            
            .preview-close:hover {
                color: #bbb;
            }
        </style>
    </head>
    <body>
        <!-- 全屏预览模态框 -->
        <div id="previewModal" class="preview-modal" onclick="closeFullscreenPreview()">
            <span class="preview-close">&times;</span>
            <div class="preview-content" id="previewContent" onclick="event.stopPropagation()"></div>
        </div>
        <!-- 全屏加载页面 -->
        <div id="loading-screen" style="
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            transition: opacity 0.5s ease;
        ">
            <div style="
                width: 60px;
                height: 60px;
                border: 4px solid rgba(255, 255, 255, 0.3);
                border-top: 4px solid white;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-bottom: 20px;
            "></div>
            <h2 style="
                color: white;
                font-size: 20px;
                font-weight: 400;
                margin: 0;
            ">正在连接服务器...</h2>
            <p style="
                color: rgba(255, 255, 255, 0.8);
                font-size: 14px;
                margin-top: 10px;
            ">请稍候，正在初始化连接</p>
        </div>
        
        <!-- 主页面容器 -->
        <div class="container" style="display: none;">
            <div class="header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h1>浅月不息 - 局域网互传</h1>
                        <p>让文件传输更简单，支持所有格式文件，无大小限制</p>
                    </div>
                    <button id="menuToggle" class="btn btn-secondary menu-toggle" style="display: none;">菜单</button>
                </div>
            </div>
            
            <div class="content">
                <!-- 连接状态提示 -->
                <div id="connection-status" class="connection-status connecting">
                    正在连接服务器...
                </div>
                
                <div class="sidebar">
                    <div class="user-info">
                        <h3>本地信息</h3>
                        <p><strong>设备名称:</strong> <span id="deviceName"></span></p>
                        <p><strong>IP地址:</strong> <span id="localIp"></span></p>
                    </div>
                    
                    <div class="online-users">
                        <h4><span class="dot"></span>在线设备</h4>
                        <ul class="user-list" id="userList">
                            <!-- 在线用户列表 -->
                        </ul>
                    </div>
                    
                    <!-- 管理记录区域 -->
                    <div class="history-management">
                        <h4>管理记录</h4>
                        <div class="history-controls">
                            <button class="btn btn-secondary btn-small" onclick="clearMessageHistory();">清除历史消息</button>
                            <button class="btn btn-secondary btn-small" onclick="exportMessageHistory();">导出历史消息</button>
                            <button class="btn btn-secondary btn-small" onclick="refreshMessages();">刷新消息</button>
                        </div>
                    </div>
                </div>
                
                <div class="chat-area">
                    <div class="messages" id="messages">
                        <!-- 消息显示区域 -->
                        <div class="message system">
                            <div class="message-header">系统消息</div>
                            <div class="message-content">欢迎使用浅月不息局域网互传工具！</div>
                        </div>
                    </div>
                    
                    <div class="input-area">
                        <div class="upload-area" id="uploadArea" onclick="document.getElementById('fileInput').click();">
                            <div class="upload-icon">📁</div>
                            <div class="upload-text">点击或拖拽文件到此处上传</div>
                            <div class="upload-hint">支持所有格式文件，无大小限制</div>
                            <input type="file" id="fileInput" multiple onchange="handleFileSelect(event);">
                        </div>
                        
                        <div class="text-input-container">
                            <textarea id="messageInput" placeholder="输入消息..." onkeydown="handleKeyPress(event);" onpaste="handlePaste(event);"></textarea>
                            <button class="btn btn-primary" onclick="sendMessage();">发送</button>
                        </div>
                        
                        <div class="transfers-section" id="transfersSection">
                            <h4>传输进度</h4>
                            <div id="activeTransfers">
                                <!-- 传输进度显示 -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 移动端菜单 -->
        <div id="mobileMenu" class="mobile-menu" style="
            position: fixed;
            top: 0;
            right: -300px;
            width: 280px;
            height: 100vh;
            background: white;
            box-shadow: -2px 0 10px rgba(0,0,0,0.2);
            z-index: 1000;
            transition: right 0.3s ease;
            display: flex;
            flex-direction: column;
        ">
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3>菜单</h3>
                    <button id="closeMenu" class="btn btn-secondary">关闭</button>
                </div>
            </div>
            <div style="padding: 15px;">
                <div class="user-info" style="margin-bottom: 20px;">
                    <h4>本地信息</h4>
                    <p><strong>设备名称:</strong> <span id="mobileDeviceName"></span></p>
                    <p><strong>IP地址:</strong> <span id="mobileLocalIp"></span></p>
                </div>
                
                <div class="online-users">
                    <h4><span class="dot"></span>在线设备</h4>
                    <ul class="user-list" id="mobileUserList">
                        <!-- 在线用户列表 -->
                    </ul>
                </div>
                
                <!-- 管理记录区域 -->
                <div class="history-management" style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee;">
                    <h4>管理记录</h4>
                    <div class="history-controls">
                        <button class="btn btn-secondary btn-small" onclick="clearMessageHistory(); closeMobileMenu();">清除历史消息</button>
                        <button class="btn btn-secondary btn-small" onclick="exportMessageHistory(); closeMobileMenu();">导出历史消息</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 半透明遮罩层 -->
        <div id="menuOverlay" class="menu-overlay" style="
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0,0,0,0.5);
            z-index: 999;
            display: none;
        "></div>
        
        <script>
            // 移动端菜单功能
            function openMobileMenu() {
                const mobileMenu = document.getElementById('mobileMenu');
                const menuOverlay = document.getElementById('menuOverlay');
                mobileMenu.style.right = '0';
                menuOverlay.style.display = 'block';
                // 更新移动端的设备信息
                document.getElementById('mobileDeviceName').textContent = document.getElementById('deviceName').textContent;
                document.getElementById('mobileLocalIp').textContent = document.getElementById('localIp').textContent;
                // 更新在线用户列表
                updateMobileUserList();
            }
            
            function closeMobileMenu() {
                const mobileMenu = document.getElementById('mobileMenu');
                const menuOverlay = document.getElementById('menuOverlay');
                mobileMenu.style.right = '-300px';
                menuOverlay.style.display = 'none';
            }
            
            function updateMobileUserList() {
                // 复用updateUserList的逻辑，但更新移动端的用户列表
                fetch('/api/users')
                    .then(response => response.json())
                    .then(data => {
                        const userList = document.getElementById('mobileUserList');
                        userList.innerHTML = '';
                        
                        data.forEach(user => {
                            const li = document.createElement('li');
                            li.className = 'user-item';
                            li.style.cursor = 'default';
                            li.style.padding = '8px 0';
                            li.style.borderBottom = '1px solid #f0f0f0';
                            li.innerHTML = `
                                <div class="user-name" style="font-weight: bold;">${user.device_name}</div>
                                <div class="user-ip" style="font-size: 12px; color: #666;">${user.ip} (${user.system_info || '未知设备'})</div>
                            `;
                            userList.appendChild(li);
                        });
                    });
            }
            
            // 聊天记录滚动到底部函数
            function scrollToBottom() {
                const messagesContainer = document.getElementById('messages');
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            // 右键菜单功能实现
            // 获取本地信息，传递deviceNickname参数以保持设备名称一致
            // 先初始化deviceNickname变量
            let deviceNickname = localStorage.getItem('deviceNickname');
            if (!deviceNickname) {
                // 默认昵称
                deviceNickname = '设备_' + Math.floor(Math.random() * 1000);
                localStorage.setItem('deviceNickname', deviceNickname);
            }
            fetch(`/api/info?device_name=${encodeURIComponent(deviceNickname)}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('连接失败');
                    }
                    return response.json();
                })
                .then(data => {
                    document.getElementById('deviceName').textContent = data.device_name;
                    document.getElementById('localIp').textContent = data.ip;
                    
                    // 确保localStorage中的deviceNickname与服务器返回的一致
                    if (data.device_name !== deviceNickname) {
                        deviceNickname = data.device_name;
                        localStorage.setItem('deviceNickname', deviceNickname);
                    }
                    
                    // 连接成功，隐藏加载页面并显示主页面
                    const loadingScreen = document.getElementById('loading-screen');
                    const container = document.querySelector('.container');
                    
                    // 显示加载成功的状态
                    loadingScreen.querySelector('h2').textContent = '连接成功！';
                    loadingScreen.querySelector('p').textContent = '正在准备界面...';
                    
                    // 延迟一小段时间，让用户看到成功信息
                    setTimeout(() => {
                        // 添加淡出动画
                        loadingScreen.classList.add('fade-out');
                        
                        // 等待动画完成后显示主页面
                        setTimeout(() => {
                            loadingScreen.style.display = 'none';
                            container.style.display = 'flex';
                        }, 500);
                    }, 1000);
                    
                    // 更新连接状态为已连接
                    const statusElement = document.getElementById('connection-status');
                    statusElement.classList.remove('connecting');
                    statusElement.classList.add('connected');
                    statusElement.textContent = '连接成功！';
                    
                    // 2秒后隐藏连接成功提示
                    setTimeout(() => {
                        statusElement.style.display = 'none';
                    }, 2000);
                })
                .catch(error => {
                    console.error('获取设备信息失败:', error);
                    // 更新加载页面显示错误信息
                    const loadingScreen = document.getElementById('loading-screen');
                    loadingScreen.querySelector('h2').textContent = '连接失败！';
                    loadingScreen.querySelector('p').textContent = '请检查网络连接后刷新页面';
                    
                    // 移除旋转动画
                    const spinner = loadingScreen.querySelector('div[style*="animation: spin"]');
                    spinner.style.animation = 'none';
                    spinner.style.backgroundColor = '#e74c3c';
                    
                    // 更新连接状态为失败
                    const statusElement = document.getElementById('connection-status');
                    statusElement.classList.remove('connecting');
                    statusElement.classList.add('failed');
                    statusElement.textContent = '连接失败，请检查网络！';
                });
            
            // 定期更新在线用户列表
            function updateUserList() {
                fetch('/api/users')
                    .then(response => response.json())
                    .then(data => {
                        const userList = document.getElementById('userList');
                        userList.innerHTML = '';
                        
                        data.forEach(user => {
                            const li = document.createElement('li');
                            li.className = 'user-item';
                            li.style.cursor = 'default';
                            li.style.padding = '8px 0';
                            li.style.borderBottom = '1px solid #f0f0f0';
                            li.innerHTML = `
                                <div class="user-name" style="font-weight: bold;">${user.device_name}</div>
                                <div class="user-ip" style="font-size: 12px; color: #666;">${user.ip} (${user.system_info || '未知设备'})</div>
                            `;
                            userList.appendChild(li);
                        });
                    });
            }
            
            // 初始更新和定时更新
            updateUserList();
            updateMobileUserList(); // 初始更新移动端用户列表
            setInterval(updateUserList, 10000);
            setInterval(updateMobileUserList, 10000); // 定时更新移动端用户列表
            
            // 页面加载完成后滚动到聊天记录底部
            window.addEventListener('load', scrollToBottom);
            
            // 菜单按钮事件监听
            const menuToggle = document.getElementById('menuToggle');
            if (menuToggle) {
                menuToggle.addEventListener('click', openMobileMenu);
            }
            
            // 关闭菜单按钮事件监听
            const closeMenu = document.getElementById('closeMenu');
            if (closeMenu) {
                closeMenu.addEventListener('click', function() {
                    closeMobileMenu();
                    // 关闭菜单后滚动到聊天记录底部
                    setTimeout(scrollToBottom, 300);
                });
            }
            
            // 遮罩层点击事件监听
            const menuOverlay = document.getElementById('menuOverlay');
            if (menuOverlay) {
                menuOverlay.addEventListener('click', function() {
                    closeMobileMenu();
                    // 关闭菜单后滚动到聊天记录底部
                    setTimeout(scrollToBottom, 300);
                });
            }
            
            // 发送消息
            let isSending = false; // 防止重复发送的标志
            let lastMessage = ''; // 上次发送的消息内容
            let lastSendTime = 0; // 上次发送时间
            const MIN_SEND_INTERVAL = 500; // 最小发送间隔（毫秒）
            
            function sendMessage() {
                const messageInput = document.getElementById('messageInput');
                const sendButton = document.querySelector('.text-input-container button');
                const message = messageInput.value.trim();
                const currentTime = Date.now();
                
                // 检查是否正在发送中
                if (isSending) {
                    return;
                }
                
                // 检查是否是重复消息且发送间隔过短
                if (message === lastMessage && (currentTime - lastSendTime) < MIN_SEND_INTERVAL) {
                    return;
                }
                
                if (message) {
                    // 设置发送中状态
                    isSending = true;
                    sendButton.disabled = true;
                    sendButton.textContent = '发送中...';
                    
                    // 添加消息ID标识，用于防止重复处理
                    const messageId = uuidv4();
                    
                    // 立即添加到消息列表，提高用户体验
                    const messages = document.getElementById('messages');
                    const ownMessageDiv = document.createElement('div');
                    ownMessageDiv.className = 'message own';
                    
                    const now = new Date();
                    const timeString = now.getHours().toString().padStart(2, '0') + ':' + 
                                      now.getMinutes().toString().padStart(2, '0');
                    
                    ownMessageDiv.innerHTML = `
                        <div class="message-header">${deviceNickname || document.getElementById('deviceName').textContent} · ${timeString}</div>
                        <div class="message-content">${message.split(String.fromCharCode(10)).join('<br>')}</div>
                    `;
                    
                    messages.appendChild(ownMessageDiv);
                    messages.scrollTop = messages.scrollHeight;
                    
                    // 为消息内容添加双击事件监听器，实现快捷复制
                    const messageContent = ownMessageDiv.querySelector('.message-content');
                    if (messageContent) {
                        messageContent.addEventListener('dblclick', function() {
                            // 获取原始消息文本（去除<br>标签）
                            const originalText = message;
                            copyToClipboard(originalText);
                        });
                    }
                    
                    // 发送到服务器
                    fetch('/api/message', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ 
                            message: message,
                            message_id: messageId,
                            client_id: clientId,
                            nickname: deviceNickname || document.getElementById('deviceName').textContent
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            // 立即清空输入框，防止用户重复点击
                            messageInput.value = '';
                            // 更新最后发送信息
                            lastMessage = message;
                            lastSendTime = currentTime;
                        } else {
                            console.error('服务器返回失败:', data.error);
                        }
                    })
                    .catch(error => {
                        console.error('发送消息失败:', error);
                        // 可以在这里显示一个错误提示
                    })
                    .finally(() => {
                        // 恢复按钮状态
                        setTimeout(() => {
                            isSending = false;
                            sendButton.disabled = false;
                            sendButton.textContent = '发送';
                        }, 300); // 稍微延迟恢复，确保用户体验
                    });
                }
            }
            
            // 处理键盘事件
            function handleKeyPress(event) {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                }
            }
            
            // 处理粘贴事件，支持粘贴图片/文件和保留文本格式
            function handlePaste(event) {
                const items = event.clipboardData.items;
                let hasText = false;
                
                // 遍历所有粘贴的项目
                for (let i = 0; i < items.length; i++) {
                    const item = items[i];
                    
                    // 检查是否是文件类型
                    if (item.kind === 'file') {
                        event.preventDefault(); // 阻止默认粘贴行为
                        const file = item.getAsFile();
                        if (file) {
                            // 调用现有的文件上传函数
                            uploadFile(file);
                        }
                    } else if (item.kind === 'string' && item.type === 'text/plain') {
                        // 处理纯文本粘贴，保留换行符
                        hasText = true;
                    }
                }
                
                // 如果是纯文本粘贴，浏览器会默认处理，保留换行符
                // 不需要额外操作，因为我们已经在显示时处理了换行符
            }
            
            // 添加消息到界面
            function addMessage(sender, content, isOwn = false) {
                const messages = document.getElementById('messages');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${isOwn ? 'own' : 'other'}`;
                
                const now = new Date();
                const timeString = now.getHours().toString().padStart(2, '0') + ':' + 
                                  now.getMinutes().toString().padStart(2, '0');
                
                messageDiv.innerHTML = `
                    <div class="message-header">${sender} · ${timeString}</div>
                    <div class="message-content">${content.split(String.fromCharCode(10)).join('<br>')}</div>
                `;
                
                messages.appendChild(messageDiv);
                messages.scrollTop = messages.scrollHeight;
                
                // 为消息内容添加双击事件监听器，实现快捷复制
                const messageContent = messageDiv.querySelector('.message-content');
                if (messageContent) {
                    messageContent.addEventListener('dblclick', function() {
                        // 获取原始消息文本（去除<br>标签）
                        const originalText = content;
                        copyToClipboard(originalText);
                    });
                }
            }
            
            // 处理文件选择
            function handleFileSelect(event) {
                const files = event.target.files;
                if (files.length > 0) {
                    for (let i = 0; i < files.length; i++) {
                        uploadFile(files[i]);
                    }
                    // 清空input以允许重复上传相同文件
                    event.target.value = '';
                }
            }
            
            // 文件上传
            function uploadFile(file) {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('client_id', clientId);
                formData.append('nickname', deviceNickname);
                formData.append('message_id', uuidv4()); // 添加唯一消息ID
                
                const transferId = 'transfer_' + Date.now();
                
                // 添加到传输列表
                const transfers = document.getElementById('activeTransfers');
                const transferItem = document.createElement('div');
                transferItem.id = transferId;
                transferItem.className = 'transfer-item';
                transferItem.innerHTML = `
                    <div class="transfer-info">
                        <span>${file.name}</span>
                        <span><span class="percent">0</span>%</span>
                    </div>
                    <div class="transfer-progress">
                        <div class="transfer-progress-bar" style="width: 0%"></div>
                    </div>
                    <div class="transfer-speed">0 MB/s</div>
                `;
                transfers.appendChild(transferItem);
                
                const xhr = new XMLHttpRequest();
                let loadedBytes = 0;
                let lastLoaded = 0;
                let lastTime = Date.now();
                
                xhr.upload.addEventListener('progress', function(e) {
                    if (e.lengthComputable) {
                        loadedBytes = e.loaded;
                        const percent = Math.round((e.loaded / e.total) * 100);
                        const progressBar = document.querySelector(`#${transferId} .transfer-progress-bar`);
                        const percentText = document.querySelector(`#${transferId} .percent`);
                        const speedText = document.querySelector(`#${transferId} .transfer-speed`);
                        
                        progressBar.style.width = percent + '%';
                        percentText.textContent = percent;
                        
                        // 计算速度
                        const currentTime = Date.now();
                        const timeDiff = (currentTime - lastTime) / 1000; // 转换为秒
                        const bytesDiff = e.loaded - lastLoaded;
                        const speed = bytesDiff / timeDiff; // 字节/秒
                        const speedMBs = (speed / (1024 * 1024)).toFixed(2); // MB/s
                        
                        speedText.textContent = speedMBs + ' MB/s';
                        
                        lastLoaded = e.loaded;
                        lastTime = currentTime;
                    }
                  });
                  
                  xhr.addEventListener('load', function() {
                    if (xhr.status === 200) {
                        // Check if response is valid JSON before parsing
                        if (xhr.responseText && xhr.responseText.trim().startsWith('<')) {
                            console.error('Received HTML instead of JSON in response:', xhr.responseText.substring(0, 100) + '...');
                            return;
                        }
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            // 不再直接添加文件消息，等待SSE推送
                            
                            // 移除传输项
                            setTimeout(() => {
                                transferItem.remove();
                            }, 2000);
                        }
                    }
                });
                
                xhr.addEventListener('error', function() {
                     console.error('上传出错');
                     alert('文件上传失败');
                     transferItem.classList.add('error');
                 });
                 
                 xhr.open('POST', '/api/upload');
                 xhr.send(formData);
             }
            
            // 文件上传函数（发送给所有人）
            function uploadFile(file) {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('client_id', clientId);
                formData.append('nickname', deviceNickname);
                formData.append('message_id', uuidv4()); // 添加唯一消息ID
                
                const transferId = 'transfer_' + Date.now();
                
                // 添加到传输列表
                const transfers = document.getElementById('activeTransfers');
                const transferItem = document.createElement('div');
                transferItem.id = transferId;
                transferItem.className = 'transfer-item';
                transferItem.innerHTML = `
                    <div class="transfer-info">
                        <span>${file.name}</span>
                        <span><span class="percent">0</span>%</span>
                    </div>
                    <div class="transfer-progress">
                        <div class="transfer-progress-bar" style="width: 0%"></div>
                    </div>
                    <div class="transfer-speed">0 MB/s</div>
                `;
                transfers.appendChild(transferItem);
                
                const xhr = new XMLHttpRequest();
                let startTime = Date.now();
                let loadedBytes = 0;
                let lastLoaded = 0;
                let lastTime = Date.now();
                
                xhr.upload.addEventListener('progress', function(e) {
                    if (e.lengthComputable) {
                        loadedBytes = e.loaded;
                        const percent = Math.round((e.loaded / e.total) * 100);
                        const progressBar = document.querySelector(`#${transferId} .transfer-progress-bar`);
                        const percentText = document.querySelector(`#${transferId} .percent`);
                        const speedText = document.querySelector(`#${transferId} .transfer-speed`);
                        
                        progressBar.style.width = percent + '%';
                        percentText.textContent = percent;
                        
                        // 计算速度
                        const currentTime = Date.now();
                        const timeDiff = (currentTime - lastTime) / 1000; // 转换为秒
                        const bytesDiff = e.loaded - lastLoaded;
                        const speed = bytesDiff / timeDiff; // 字节/秒
                        const speedMBs = (speed / (1024 * 1024)).toFixed(2); // MB/s
                        
                        speedText.textContent = speedMBs + ' MB/s';
                        
                        lastLoaded = e.loaded;
                        lastTime = currentTime;
                    }
                });
                
                xhr.addEventListener('load', function() {
                    if (xhr.status === 200) {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            // 不再直接添加文件消息，等待SSE推送
                            // 移除文件消息DOM操作，避免重复显示
                            // 文件将通过SSE机制自动接收并显示在消息列表中
                            
                            // 移除传输项
                            setTimeout(() => {
                                transferItem.remove();
                            }, 2000);
                        }
                    }
                });
                
                xhr.addEventListener('error', function() {
                    alert('文件上传失败');
                    transferItem.remove();
                });
                
                xhr.open('POST', '/api/upload');
                xhr.send(formData);
            }
            
            // 格式化文件大小
            function formatFileSize(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }
            
            // 截断过长的文件名
            function truncateFilename(filename, maxLength = 20) {
                if (!filename || filename.length <= maxLength) {
                    return filename;
                }
                const dotIndex = filename.lastIndexOf('.');
                const extension = dotIndex !== -1 ? filename.substring(dotIndex) : '';
                const nameWithoutExt = dotIndex !== -1 ? filename.substring(0, dotIndex) : filename;
                const maxNameLength = maxLength - extension.length - 3; // 减去省略号的长度
                
                if (maxNameLength <= 0) {
                    // 如果扩展名太长，只显示部分扩展名
                    return filename.substring(0, maxLength - 3) + '...';
                }
                
                return nameWithoutExt.substring(0, maxNameLength) + '...' + extension;
            }
            
            // 生成UUID的辅助函数
            function uuidv4() {
                return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    const r = Math.random() * 16 | 0;
                    const v = c === 'x' ? r : (r & 0x3 | 0x8);
                    return v.toString(16);
                });
            }
            
            // 复制文本到剪贴板的辅助函数
            function copyToClipboard(text) {
                navigator.clipboard.writeText(text)
                    .then(() => {
                        // 可以添加一个复制成功的提示
                        console.log('文本已复制到剪贴板');
                    })
                    .catch(err => {
                        console.error('复制失败:', err);
                    });
            }
            
            // 存储已处理的消息ID，防止重复显示
            let processedMessageIds = new Set();
            
            // 根据文件扩展名获取对应的图标
            function getFileIcon(filename) {
                // 获取文件扩展名（转为小写）
                const extension = filename.split('.').pop().toLowerCase();
                
                // 图片文件
                const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'];
                if (imageExtensions.includes(extension)) {
                    return '🖼️';
                }
                
                // 视频文件
                const videoExtensions = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'];
                if (videoExtensions.includes(extension)) {
                    return '🎬';
                }
                
                // 音频文件
                const audioExtensions = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'];
                if (audioExtensions.includes(extension)) {
                    return '🎵';
                }
                
                // 文档文件
                const docExtensions = ['doc', 'docx'];
                if (docExtensions.includes(extension)) {
                    return '📝';
                }
                
                // PDF文件
                if (extension === 'pdf') {
                    return '📄';
                }
                
                // PPT文件
                const pptExtensions = ['ppt', 'pptx'];
                if (pptExtensions.includes(extension)) {
                    return '📊';
                }
                
                // Excel文件
                const excelExtensions = ['xls', 'xlsx', 'csv'];
                if (excelExtensions.includes(extension)) {
                    return '📈';
                }
                
                // 压缩文件
                const archiveExtensions = ['zip', 'rar', '7z', 'tar', 'gz'];
                if (archiveExtensions.includes(extension)) {
                    return '🗜️';
                }
                
                // 代码文件
                const codeExtensions = ['js', 'html', 'css', 'py', 'java', 'cpp', 'c', 'php', 'go', 'rb', 'swift', 'kotlin'];
                if (codeExtensions.includes(extension)) {
                    return '💻';
                }
                
                // Android APK
                if (extension === 'apk') {
                    return '🤖';
                }
                
                // iOS文件
                if (extension === 'ipa') {
                    return '📱';
                }
                
                // 文本文件
                if (extension === 'txt') {
                    return '📄';
                }
                
                // 其他文件默认图标
                return '📎';
            }
            
            // 全屏预览功能
            function openFullscreenPreview(url) {
                const modal = document.getElementById('previewModal');
                const previewContent = document.getElementById('previewContent');
                
                // 清空预览内容
                previewContent.innerHTML = '';
                
                // 根据URL判断文件类型
                const extension = url.split('.').pop().toLowerCase();
                
                if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(extension)) {
                    // 图片预览
                    const img = document.createElement('img');
                    img.src = url;
                    img.onload = function() {
                        modal.style.display = 'flex';
                        document.body.style.overflow = 'hidden'; // 防止背景滚动
                    };
                    previewContent.appendChild(img);
                } else if (['mp4', 'webm', 'ogg'].includes(extension)) {
                    // 视频预览
                    const video = document.createElement('video');
                    video.src = url;
                    video.controls = true;
                    video.autoplay = false;
                    video.oncanplay = function() {
                        modal.style.display = 'flex';
                        document.body.style.overflow = 'hidden';
                    };
                    previewContent.appendChild(video);
                } else if (['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(extension)) {
                    // 音频预览（在全屏模态框中）
                    const audio = document.createElement('audio');
                    audio.src = url;
                    audio.controls = true;
                    audio.autoplay = false;
                    audio.style.width = '400px';
                    audio.style.maxWidth = '90%';
                    audio.style.background = 'white';
                    audio.style.padding = '20px';
                    audio.style.borderRadius = '12px';
                    audio.oncanplay = function() {
                        modal.style.display = 'flex';
                        document.body.style.overflow = 'hidden';
                    };
                    previewContent.appendChild(audio);
                }
            }
            
            function closeFullscreenPreview() {
                const modal = document.getElementById('previewModal');
                const previewContent = document.getElementById('previewContent');
                
                // 暂停媒体播放
                const mediaElement = previewContent.querySelector('video, audio');
                if (mediaElement) {
                    mediaElement.pause();
                }
                
                modal.style.display = 'none';
                document.body.style.overflow = 'auto'; // 恢复背景滚动
            }
            
            // 拖拽上传支持
            const uploadArea = document.getElementById('uploadArea');
            
            uploadArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                uploadArea.classList.add('active');
            });
            
            uploadArea.addEventListener('dragleave', function() {
                uploadArea.classList.remove('active');
            });
            
            uploadArea.addEventListener('drop', function(e) {
                e.preventDefault();
                uploadArea.classList.remove('active');
                
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    for (let i = 0; i < files.length; i++) {
                        uploadFile(files[i]);
                    }
                }
            });
            
            // 生成或获取客户端ID（deviceNickname已在前面初始化）
            let clientId = localStorage.getItem('clientId');
            
            if (!clientId) {
                clientId = uuidv4();
                localStorage.setItem('clientId', clientId);
            }
            
            // 显示并允许用户编辑昵称
            const nicknameDisplay = document.createElement('div');
            nicknameDisplay.className = 'nickname-display';
            nicknameDisplay.innerHTML = `
                <span>昵称: </span>
                <input type="text" id="nicknameInput" value="${deviceNickname}" placeholder="请输入昵称">
                <button id="saveNickname">保存</button>
            `;
            const sidebar = document.getElementById('sidebar');
            if (sidebar) {
                sidebar.prepend(nicknameDisplay);
                
                // 只有当sidebar存在时才设置保存按钮的点击事件
                const saveButton = document.getElementById('saveNickname');
                if (saveButton) {
                    saveButton.onclick = function() {
                        const nicknameInput = document.getElementById('nicknameInput');
                        if (nicknameInput) {
                            const newNickname = nicknameInput.value.trim();
                            if (newNickname) {
                                deviceNickname = newNickname;
                                localStorage.setItem('deviceNickname', deviceNickname);
                                alert('昵称已保存');
                            }
                        }
                    };
                }
            } else {
                console.log('侧边栏元素未找到，跳过昵称显示添加');
            }
            
            // 建立SSE连接接收实时消息
            function connectToEvents() {
                // 先关闭可能存在的旧连接
                if (window.currentEventSource) {
                    try {
                        window.currentEventSource.close();
                        console.log('已关闭旧的SSE连接');
                    } catch (e) {
                        console.error('关闭旧SSE连接时出错:', e);
                    }
                }
                
                // 添加client_id和昵称参数，帮助服务器管理连接和识别设备
                // 添加时间戳参数防止缓存
                const eventSourceUrl = `/api/events?client_id=${clientId}&nickname=${encodeURIComponent(deviceNickname)}&t=${Date.now()}`;
                console.log('建立新的SSE连接:', eventSourceUrl);
                
                try {
                    window.currentEventSource = new EventSource(eventSourceUrl);
                    
                    window.currentEventSource.onopen = function() {
                        console.log('SSE连接已建立');
                    };
                    
                    window.currentEventSource.onmessage = function(event) {
                        try {
                            // Check if data starts with '<' which indicates HTML response
                            if (event.data && event.data.trim().startsWith('<')) {
                                console.warn('Received HTML instead of JSON:', event.data.substring(0, 100) + '...');
                                return; // Skip processing HTML content
                            }
                            
                            const data = JSON.parse(event.data);
                            // 忽略心跳消息
                            if (!data || Object.keys(data).length === 0) return;
                            
                            // 使用client_id而不是IP来判断是否为自己发送的消息
                            const isOwn = data.client_id === clientId;
                            
                            // 获取消息容器
                            const messages = document.getElementById('messages');
                            if (!messages) {
                                console.error('消息容器元素未找到');
                                return;
                            }
                            
                            // 处理聊天历史消息 - 每秒广播的完整历史
                            if (data.type === 'history' && data.history) {
                                // 清空现有的已处理消息ID，准备重新加载所有消息
                                // 但保留最近的50条消息ID，避免频繁重建DOM
                                const recentIds = Array.from(processedMessageIds).slice(-50);
                                processedMessageIds.clear();
                                recentIds.forEach(id => processedMessageIds.add(id));
                                
                                // 处理每条历史消息
                                data.history.forEach(historyMsg => {
                                    const msgIsOwn = historyMsg.client_id === clientId;
                                    const msgType = historyMsg.type || 'text';
                                    
                                    if (msgType === 'file' && historyMsg.file) {
                                        // 处理文件消息
                                        if (shouldShowMessage(historyMsg)) {
                                            addFileMessage(historyMsg, msgIsOwn);
                                        }
                                    } else if (msgType === 'text' && historyMsg.message) {
                                // 处理文本消息
                                // 首先检查是否应该显示此消息
                                if (!shouldShowMessage(historyMsg)) {
                                    return;
                                }
                                
                                const messageId = historyMsg.message_id || (historyMsg.timestamp + '_' + (historyMsg.message || '').substring(0, 20));
                                
                                // 跳过已处理的消息
                                if (processedMessageIds.has(messageId)) {
                                    return;
                                }
                                processedMessageIds.add(messageId);
                                
                                // 限制存储的消息ID数量
                                if (processedMessageIds.size > 1000) {
                                    const firstId = processedMessageIds.values().next().value;
                                    processedMessageIds.delete(firstId);
                                }
                                
                                // 如果消息已存在于DOM中，跳过
                                if (messages.querySelector(`[data-message-id="${messageId}"]`)) {
                                    return;
                                }
                                
                                const messageDiv = document.createElement('div');
                                messageDiv.className = `message ${msgIsOwn ? 'own' : 'other'}`;
                                messageDiv.setAttribute('data-message-id', messageId);
                                
                                const time = new Date(historyMsg.timestamp);
                                const timeString = time.getHours().toString().padStart(2, '0') + ':' + 
                                                  time.getMinutes().toString().padStart(2, '0');
                                
                                messageDiv.innerHTML = `
                                    <div class="message-header">${historyMsg.sender || '未知用户'} · ${timeString}</div>
                                    <div class="message-content">${historyMsg.message.split(String.fromCharCode(10)).join('<br>')}</div>
                                `;
                                
                                messages.appendChild(messageDiv);
                                
                                // 为消息内容添加双击事件监听器，实现快捷复制
                                const messageContent = messageDiv.querySelector('.message-content');
                                if (messageContent) {
                                    messageContent.addEventListener('dblclick', function() {
                                        // 获取原始消息文本（去除<br>标签）
                                        const originalText = historyMsg.message;
                                        copyToClipboard(originalText);
                                    });
                                }
                                    }
                                });
                                
                                // 滚动到底部
                                messages.scrollTop = messages.scrollHeight;
                            }
                            // 处理单条文本消息
                            else if (data.type === 'text' && data.message) {
                                // 使用后端传递的message_id或生成临时ID
                                const messageId = data.message_id || (data.timestamp + '_' + data.message.substring(0, 20));
                                
                                // 检查是否已处理过此消息ID
                                if (processedMessageIds.has(messageId)) {
                                    return; // 跳过重复消息
                                }
                                processedMessageIds.add(messageId);
                                // 限制存储的消息ID数量，防止内存占用过大
                                if (processedMessageIds.size > 1000) {
                                    // 移除最早的消息ID
                                    const firstId = processedMessageIds.values().next().value;
                                    processedMessageIds.delete(firstId);
                                }
                                
                                if (!messages.querySelector(`[data-message-id="${messageId}"]`)) {
                                    const messageDiv = document.createElement('div');
                                    messageDiv.className = `message ${isOwn ? 'own' : 'other'}`;
                                    messageDiv.setAttribute('data-message-id', messageId);
                                    
                                    const time = new Date(data.timestamp);
                                    const timeString = time.getHours().toString().padStart(2, '0') + ':' + 
                                                      time.getMinutes().toString().padStart(2, '0');
                                    
                                    messageDiv.innerHTML = `
                                        <div class="message-header">${data.sender} · ${timeString}</div>
                                        <div class="message-content">${data.message.split(String.fromCharCode(10)).join('<br>')}</div>
                                    `;
                                    
                                    messages.appendChild(messageDiv);
                                    messages.scrollTop = messages.scrollHeight;
                                    
                                    // 为消息内容添加双击事件监听器，实现快捷复制
                                    const messageContent = messageDiv.querySelector('.message-content');
                                    if (messageContent) {
                                        messageContent.addEventListener('dblclick', function() {
                                            // 获取原始消息文本（去除<br>标签）
                                            const originalText = data.message;
                                            copyToClipboard(originalText);
                                        });
                                    }
                                }
                            }
                            // 处理文件消息
                            else if (data.type === 'file' && data.file) {
                                // 使用统一的判断逻辑检查是否应该显示此消息
                                if (shouldShowMessage(data)) {
                                    addFileMessage(data, isOwn);
                                }
                            } else if (data.type === 'text' && !data.message) {
                                // 只处理没有消息内容的文本消息（如果有的话）
                                addMessage(data.sender, data.message || '', isOwn);
                            }
                        } catch (e) {
                            console.error('处理消息时出错:', e, '消息数据:', event.data);
                        }
                    };
                    
                    window.currentEventSource.onerror = function(error) {
                        console.error('SSE连接错误:', error);
                        // 确保连接已关闭
                        try {
                            window.currentEventSource.close();
                        } catch (e) {
                            console.error('关闭错误的SSE连接时出错:', e);
                        }
                        
                        // 使用指数退避策略重连
                        let retryDelay = 2000; // 初始2秒
                        const maxRetryDelay = 30000; // 最大30秒
                        
                        const reconnect = function() {
                            console.log(`尝试重新连接SSE，延迟${retryDelay}ms`);
                            connectToEvents();
                        };
                        
                        setTimeout(reconnect, retryDelay);
                    };
                } catch (e) {
                    console.error('创建SSE连接失败:', e);
                    // 立即尝试重连
                    setTimeout(connectToEvents, 2000);
                }
            }
            
            let lastMessageCount = 0; // 初始化消息计数变量
            
            // 判断是否应该显示消息
            function shouldShowMessage(msg) {
                // 检查是否是自己发送的消息，如果是则不显示（避免重复）
                if (msg && msg.client_id && msg.client_id === clientId) {
                    return false;
                }
                return true;
            }
            
            // 添加文件消息
            function addFileMessage(msg, isOwn) {
                const messages = document.getElementById('messages');
                if (!messages) return;
                
                // 使用后端传递的message_id作为唯一标识
                const messageId = msg.message_id || msg.file.transfer_id || msg.file.unique_filename || msg.timestamp;
                
                // 检查是否已处理过此消息ID
                if (processedMessageIds.has(messageId)) {
                    return; // 跳过重复消息
                }
                processedMessageIds.add(messageId);
                // 限制存储的消息ID数量，防止内存占用过大
                if (processedMessageIds.size > 1000) {
                    // 移除最早的消息ID
                    const firstId = processedMessageIds.values().next().value;
                    processedMessageIds.delete(firstId);
                }
                
                if (messages.querySelector(`[data-message-id="${messageId}"]`)) return;
                
                const fileMessage = document.createElement('div');
                fileMessage.className = `message ${isOwn ? 'own' : 'other'}`;
                fileMessage.setAttribute('data-message-id', messageId);
                
                const time = new Date(msg.timestamp);
                const timeString = time.getHours().toString().padStart(2, '0') + ':' + 
                                  time.getMinutes().toString().padStart(2, '0');
                
                const fileIcon = getFileIcon(msg.file.filename);
                const extension = msg.file.filename.split('.').pop().toLowerCase();
                
                // 检查是否为可预览文件
                let previewHtml = '';
                const previewableExtensions = {
                    image: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'],
                    audio: ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'],
                    video: ['mp4', 'webm', 'ogg']
                };
                
                const previewUrl = `/api/download/${msg.file.unique_filename}`;
                
                if (previewableExtensions.image.includes(extension)) {
                    previewHtml = `<div class="file-preview file-preview-image"><img src="${previewUrl}" alt="${msg.file.filename}" onclick="openFullscreenPreview('${previewUrl}')" /></div>`;
                } else if (previewableExtensions.audio.includes(extension)) {
                    previewHtml = `<div class="file-preview file-preview-audio"><audio controls src="${previewUrl}"></audio></div>`;
                } else if (previewableExtensions.video.includes(extension)) {
                    previewHtml = `<div class="file-preview file-preview-video"><video controls src="${previewUrl}"></video></div>`;
                }
                
                // 简化消息头部，移除专属文件标记
                const messageHeader = `${msg.sender} · ${timeString}`;
                
                fileMessage.innerHTML = `
                    <div class="message-header">${messageHeader}</div>
                    <div class="file-message">
                        ${previewHtml}
                        <div class="file-info">
                            <div class="file-icon">${fileIcon}</div>
                            <div class="file-details">
                                <div class="file-name" title="${msg.file.filename}">${truncateFilename(msg.file.filename)}</div>
                                <div class="file-size">${formatFileSize(msg.file.size)}</div>
                            </div>
                        </div>
                        <div class="file-actions">
                            <button class="btn btn-primary" onclick="downloadFile('${msg.file.unique_filename}', '${msg.file.filename}')">下载</button>
                        </div>
                    </div>
                `;
                
                messages.appendChild(fileMessage);
                messages.scrollTop = messages.scrollHeight;
            }
            
            // 加载消息历史并处理专属文件逻辑
            function loadMessages(forceRefresh = false) {
                fetch('/api/messages')
                    .then(response => response.json())
                    .then(data => {
                        if (forceRefresh) {
                            // 强制刷新：清空现有消息并重新加载所有消息
                            const messages = document.getElementById('messages');
                            // 保留系统欢迎消息
                            const systemWelcome = messages.querySelector('.message.system');
                            messages.innerHTML = '';
                            if (systemWelcome) {
                                messages.appendChild(systemWelcome);
                            }
                            
                            // 重新加载所有消息
                            data.forEach(msg => {
                                // 使用client_id而不是IP来判断是否为自己发送的消息
                                const isOwn = msg.client_id === clientId;
                                
                                // 处理专属文件判断逻辑
                                if (shouldShowMessage(msg)) {
                                    if (msg.file) {
                                        addFileMessage(msg, isOwn);
                                    } else {
                                        // 添加文本消息
                                        addMessage(msg.sender, msg.message, isOwn);
                                    }
                                }
                            });
                            lastMessageCount = data.length;
                        } else if (data.length > lastMessageCount) {
                            // 如果有新消息，只显示新消息
                            const newMessages = data.slice(lastMessageCount);
                            newMessages.forEach(msg => {
                                // 使用client_id而不是IP来判断是否为自己发送的消息
                                const isOwn = msg.client_id === clientId;
                                
                                // 处理专属文件判断逻辑
                                if (shouldShowMessage(msg)) {
                                    if (msg.file) {
                                        addFileMessage(msg, isOwn);
                                    } else {
                                        // 添加文本消息
                                        addMessage(msg.sender, msg.message, isOwn);
                                    }
                                }
                            });
                            lastMessageCount = data.length;
                        }
                    })
                    .catch(error => {
                        console.error('加载消息历史失败:', error);
                    });
            }
            
            // 刷新消息函数
            function refreshMessages() {
                loadMessages(true);
            }
            
            // 保持兼容的初始加载函数
            function loadInitialMessages() {
                loadMessages();
            }
            
            // 下载文件函数
            function downloadFile(uniqueFilename, originalFilename) {
                // 创建一个临时链接来触发下载
                const link = document.createElement('a');
                link.href = `/api/download/${uniqueFilename}`;
                link.download = originalFilename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
            
            // 定期检查活跃传输并刷新消息
            function checkActiveTransfers() {
                fetch('/api/transfers')
                    .then(response => response.json())
                    .then(data => {
                        // 仅更新传输状态，不再加载消息（由SSE负责）
                    })
                    .catch(error => {
                        console.error('检查活跃传输失败:', error);
                    });
            }
            
            // 确保页面加载完成后滚动到底部
            function ensureScrollToBottom() {
                const messages = document.getElementById('messages');
                if (messages) {
                    messages.scrollTop = messages.scrollHeight;
                }
            }

            // 启动SSE连接和加载初始消息
            setTimeout(() => {
                // 先检查是否已经有活动的EventSource连接
                if (window.currentEventSource) {
                    try {
                        window.currentEventSource.close();
                    } catch (e) {
                        console.log('关闭现有连接时出错:', e);
                    }
                }
                connectToEvents();
                loadInitialMessages();
                
                // 确保消息加载后滚动到底部
                setTimeout(ensureScrollToBottom, 500);
            }, 1000);
            
            // 页面加载完成后也滚动到底部
            window.addEventListener('load', ensureScrollToBottom);
            window.addEventListener('resize', ensureScrollToBottom);
            
            // 保留传输检查（每1秒）
            setInterval(checkActiveTransfers, 1000);
            
            // 添加每10秒自动刷新消息的功能
            setInterval(() => {
                loadMessages(false); // 非强制刷新，只加载新消息
            }, 10000);
            
            // 清除历史消息
            function clearMessageHistory() {
                // 直接执行清除操作，不需要二次确认
                fetch('/api/clear-history', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // 清空消息列表
                        document.getElementById('messages').innerHTML = `
                            <div class="message system">
                                <div class="message-header">系统消息</div>
                                <div class="message-content">历史消息已清除</div>
                            </div>
                        `;
                        lastMessageCount = 0;
                        alert('历史消息已清除');
                    }
                })
                .catch(error => {
                    console.error('清除历史消息失败:', error);
                    alert('清除历史消息失败');
                });
            }
            
            // 导出历史消息
            function exportMessageHistory() {
                fetch('/api/export-history')
                    .then(response => response.json())
                    .then(data => {
                        if (data.success && data.history) {
                            // 创建下载链接
                            const blob = new Blob([JSON.stringify(data.history, null, 2)], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `message_history_${new Date().toISOString().slice(0,10)}.json`;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                        }
                    })
                    .catch(error => {
                        console.error('导出历史消息失败:', error);
                        alert('导出历史消息失败');
                    });
            }
        </script>
    </body>
    </html>
    ''')

# 获取本地信息
@app.route('/api/info', methods=['GET', 'POST'])
def get_info():
    # 使用客户端的IP地址而不是服务器的IP
    client_ip = request.remote_addr
    port = 5000  # 默认端口
    
    # 使用客户端用户代理信息来识别设备类型
    user_agent = request.headers.get('User-Agent', '')
    
    # 初始化系统信息为默认值
    system_info = '未知'
    
    # 根据用户代理字符串识别设备类型
    if 'Android' in user_agent:
        system_info = 'Android'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        system_info = 'iOS'
    elif 'Windows' in user_agent:
        system_info = 'Windows'
    elif 'Macintosh' in user_agent:
        system_info = 'macOS'
    elif 'Linux' in user_agent:
        system_info = 'Linux'
    
    # 首先检查请求中是否有提供设备名称（支持GET和POST）
    device_name = None
    if request.method == 'POST':
        data = request.get_json() or {}
        device_name = data.get('device_name')
    else:
        device_name = request.args.get('device_name')
    
    # 如果请求中没有提供设备名称，尝试从online_users中获取已注册的昵称
    if not device_name:
        with lock:
            if client_ip in online_users and 'nickname' in online_users[client_ip]:
                device_name = online_users[client_ip]['nickname']
    
    # 如果仍然没有设备名称，才生成一个新的随机名称
    if not device_name:
        import random
        # 生成设备编号，使用与前端相同的格式（0-999）
        device_id = random.randint(0, 999)
        device_name = f"设备_{device_id}"
    
    # 注册当前客户端为活跃设备
    register_client(client_ip, device_name)
    
    return jsonify({
        'device_name': device_name,
        'ip': f"{client_ip}:{port}"
    })


# register_client函数已在文件其他位置定义，此处不再重复定义

# 获取在线用户
@app.route('/api/users')
def get_users():
    # 清理离线用户（超过30秒未更新）
    current_time = datetime.now()
    for user_ip, user_info in list(online_users.items()):
        # 只清理使用IP作为键且有last_seen字段的用户（客户端用户）
        if isinstance(user_ip, str) and '.' in user_ip and 'last_seen' in user_info:
            if (current_time - user_info['last_seen']).total_seconds() > 30:
                with lock:
                    del online_users[user_ip]
    
    # 只返回使用IP作为键的客户端用户（过滤掉使用client_id作为键的SSE连接）
    active_users = []
    with lock:
        for user_ip, user_info in online_users.items():
            # 只包含IP格式的键（客户端用户）
            if isinstance(user_ip, str) and '.' in user_ip:
                # 获取系统信息（如果有）
                system_info = user_info.get('system_info', '未知设备')
                active_users.append({
                    'device_name': user_info.get('device_name', f'设备-{user_ip}'),
                    'ip': user_info.get('ip', f'{user_ip}:5000'),
                    'system_info': system_info,
                    'client_id': user_info.get('client_id', 'unknown')
                })
    
    return jsonify(active_users)

# 发现局域网内的其他设备 - 现在只在需要时手动扫描，不再自动扫描整个局域网
def discover_lan_devices():
    # 移除自动扫描整个局域网的功能
    # 只保留空函数，因为其他地方调用了这个函数
    pass

# 客户端主动注册函数
def register_client(ip, device_name):
    """只有当客户端主动访问页面时才调用此函数注册设备"""
    # 从设备名称尝试提取系统信息
    system_info = '未知设备'
    user_agent = request.headers.get('User-Agent', '')
    if 'Android' in user_agent:
        system_info = 'Android'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        system_info = 'iOS'
    elif 'Windows' in user_agent:
        system_info = 'Windows'
    elif 'Macintosh' in user_agent:
        system_info = 'macOS'
    elif 'Linux' in user_agent:
        system_info = 'Linux'
    
    with lock:
        online_users[ip] = {
            'device_name': device_name,
            'ip': f"{ip}:5000",
            'system_info': system_info,
            'last_seen': datetime.now(),
            'active': True  # 标记为主动活跃设备
        }

# 服务器发送事件 (SSE) 端点，用于实时消息通知
@app.route('/api/events')
def events():
    # 获取客户端标识和昵称，用于管理连接和识别设备
    client_id = request.args.get('client_id', str(uuid.uuid4()))
    nickname = request.args.get('nickname', f'设备_{client_id[:8]}')
    client_ip = request.remote_addr
    
    # 使用IP地址作为键更新现有用户的昵称和最后在线时间
    # 如果用户不存在，也创建新条目
    with lock:
        if client_ip not in online_users:
            online_users[client_ip] = {
                'device_name': f"设备_{client_ip}",
                'ip': f"{client_ip}:5000",
                'last_seen': datetime.now(),
                'active': True
            }
        online_users[client_ip]['nickname'] = nickname
        online_users[client_ip]['client_id'] = client_id
        online_users[client_ip]['last_seen'] = datetime.now()
    
    def generate():
        # 使用字典存储消息队列，便于通过client_id识别
        # 修改callback_responses结构，包含client_ip和client_id信息，用于消息定向发送
        callback_responses = {'id': client_id, 'client_id': client_id, 'client_ip': client_ip, 'queue': []}
        
        with lock:
            # 清理该客户端可能存在的旧连接
            message_callbacks[:] = [cb for cb in message_callbacks if not isinstance(cb, dict) or cb['id'] != client_id]
            message_callbacks.append(callback_responses)
        
        try:
            # 记录上次心跳时间
            last_heartbeat = datetime.now()
            heartbeat_interval = 15  # 心跳间隔15秒，小于清理时间30秒
            # 保持连接打开
            while True:
                # 检查是否有新消息需要发送
                with lock:
                    if callback_responses['queue']:
                        message = callback_responses['queue'].pop(0)
                        yield f"data: {json.dumps(message)}\n\n"
                    
                    # 每一秒广播聊天记录
                        # 将整个聊天历史作为消息发送给客户端，但过滤掉当前用户自己发送的消息
                        # 只包含其他用户的消息和系统消息
                        filtered_history = []
                        for msg in message_history:
                            # 如果消息有client_id且与当前客户端ID相同，则跳过
                            if 'client_id' in msg and msg['client_id'] == client_id:
                                continue
                            filtered_history.append(msg)
                        
                        history_message = {
                            'type': 'history',
                            'history': filtered_history,
                            'timestamp': datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(history_message)}\n\n"
                
                # 检查是否需要发送心跳并更新用户活动时间
                current_time = datetime.now()
                if (current_time - last_heartbeat).total_seconds() > heartbeat_interval:
                    # 更新用户的最后活跃时间
                    with lock:
                        if client_ip in online_users:
                            online_users[client_ip]['last_seen'] = current_time
                            logger.debug(f"心跳更新 - IP: {client_ip}, 时间: {current_time}")
                    last_heartbeat = current_time
                
                time.sleep(1)  # 每秒执行一次循环，包括广播聊天记录
        except GeneratorExit:
            # 连接关闭时，从回调列表中移除
            with lock:
                message_callbacks[:] = [cb for cb in message_callbacks if cb != callback_responses]
                # 不要立即删除用户，给用户短暂的重连时间
                # 保留用户信息，但不更新最后活跃时间
                # 用户会在/api/users请求中根据last_seen字段自动清理（超过30秒）
        except Exception as e:
            logger.error(f"SSE错误 (客户端 {client_id}): {str(e)}")
    
    # 设置响应头
    return app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

# 存储已处理的消息ID，防止重复处理
processed_message_ids = set()

# 发送消息
@app.route('/api/message', methods=['POST'])
def send_message():
    data = request.json
    message = data.get('message', '')
    message_id = data.get('message_id', '')
    
    if message:
        hostname = socket.gethostname()
        ip = request.remote_addr  # 使用客户端真实IP地址
        current_time = datetime.now().timestamp()
        
        # 检查是否在短时间内发送了相同的消息
        with lock:
            # 检查消息ID是否已处理，防止重复消息
            if message_id and message_id in processed_message_ids:
                logger.info(f"拒绝重复消息ID: {message_id}")
                return jsonify({'success': True})
                
            # 检查是否在短时间内发送了相同内容的消息
            if ip in recent_messages:
                recent = recent_messages[ip]
                # 如果消息相同且时间间隔小于最小间隔，拒绝发送
                if recent['last_message'] == message and (current_time - recent['timestamp']) < MIN_MESSAGE_INTERVAL:
                    logger.info(f"拒绝重复消息: {hostname} - {message}")
                    return jsonify({'success': True})  # 返回成功但不处理，避免前端报错
        
        # 获取客户端ID和昵称
        client_id = data.get('client_id', str(uuid.uuid4()))
        nickname = data.get('nickname', hostname)
        
        # 创建消息对象
        new_message = {
            'sender': nickname,
            'sender_ip': ip,
            'client_id': client_id,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'type': 'text',
            'message_id': message_id  # 添加消息ID
        }
        
        # 添加到消息历史并通知所有客户端
        with lock:
            # 记录已处理的消息ID
            if message_id:
                processed_message_ids.add(message_id)
                # 清理过期的消息ID记录（保留最近1000个）
                if len(processed_message_ids) > 1000:
                    # 移除最早的消息ID（近似实现）
                    processed_message_ids.pop()
            
            # 更新最近消息记录
            recent_messages[ip] = {
                'last_message': message,
                'timestamp': current_time
            }
            
            message_history.append(new_message)
            
            # 限制消息历史长度
            if len(message_history) > 100:
                message_history.pop(0)
            
            # 保存历史消息到文件
            save_message_history(message_history)
        
        # 通知客户端
        with lock:
            for callback_dict in message_callbacks[:]:  # 使用副本迭代，避免在迭代过程中修改列表
                try:
                    # 确保是正确的字典格式并且包含queue字段
                    if isinstance(callback_dict, dict) and 'queue' in callback_dict:
                        # 获取客户端信息
                        callback_client_id = callback_dict.get('client_id', callback_dict.get('id', ''))
                        callback_client_ip = callback_dict.get('client_ip', '')
                        
                        # 广播消息：发送给所有客户端（除了发送者自己）
                        if callback_client_id != client_id:
                            callback_dict['queue'].append(new_message)
                except Exception as e:
                    logger.error(f"将消息添加到客户端队列时出错: {e}")
        
        # 获取主机名用于日志记录
        current_hostname = socket.gethostname()
        logger.info(f"消息发送成功: {current_hostname} - {message}")
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': '消息不能为空'})

# 获取消息历史
@app.route('/api/messages')
def get_messages():
    # 清理过期消息（超过1小时）
    current_time = datetime.now()
    message_history[:] = [msg for msg in message_history 
                         if (current_time - datetime.fromisoformat(msg['timestamp'])).total_seconds() < 3600]
    
    return jsonify(message_history)

# 文件上传
@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有文件部分'})
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'})
    
    # 获取客户端ID和昵称
    client_id = request.form.get('client_id', str(uuid.uuid4()))
    nickname = request.form.get('nickname', socket.gethostname())
    message_id = request.form.get('message_id', str(uuid.uuid4()))  # 生成唯一消息ID
    
    # 获取接收者信息（如果有）
    recipient_ip = request.form.get('recipient_ip')
    recipient_name = request.form.get('recipient_name')
    recipient_client_id = request.form.get('recipient_client_id')
    
    # 生成唯一文件名
    unique_filename = str(uuid.uuid4()) + '_' + file.filename
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    
    # 创建传输ID
    transfer_id = str(uuid.uuid4())
    
    # 存储传输信息
    with lock:
        active_transfers[transfer_id] = {
            'filename': file.filename,
            'unique_filename': unique_filename,
            'size': request.content_length or 0,
            'transferred': 0,
            'status': 'in_progress',
            'timestamp': datetime.now().isoformat()
        }
    
    try:
        # 保存文件
        file.save(file_path)
        
        # 更新传输状态
        with lock:
            active_transfers[transfer_id]['status'] = 'completed'
            active_transfers[transfer_id]['transferred'] = os.path.getsize(file_path)
            active_transfers[transfer_id]['size'] = os.path.getsize(file_path)
        
        # 创建文件消息
        ip = request.remote_addr
        
        # 简化为只广播文件传输消息
        file_message = {
            'sender': nickname,
            'sender_ip': ip,
            'client_id': client_id,
            'message': f'分享了文件: {file.filename}',
            'timestamp': datetime.now().isoformat(),
            'type': 'file',
            'message_id': message_id,  # 添加消息ID
            'file': {
                'transfer_id': transfer_id,
                'filename': file.filename,
                'unique_filename': unique_filename,
                'size': active_transfers[transfer_id]['size']
            }
        }
        
        # 添加到消息历史并通知客户端
        with lock:
            message_history.append(file_message)
            
            # 限制消息历史长度
            if len(message_history) > 100:
                message_history.pop(0)
            
            # 保存历史消息到文件
            save_message_history(message_history)
            
            # 记录已处理的消息ID
            processed_message_ids.add(message_id)
            # 清理过期的消息ID记录（保留最近1000个）
            if len(processed_message_ids) > 1000:
                # 移除最早的消息ID（近似实现）
                processed_message_ids.pop()
            
            # 通知客户端
            for callback_dict in message_callbacks[:]:  # 使用副本迭代，避免在迭代过程中修改列表
                try:
                    # 确保是正确的字典格式并且包含queue字段
                    if isinstance(callback_dict, dict) and 'queue' in callback_dict and 'client_ip' in callback_dict:
                        # 获取客户端信息
                        client_ip = callback_dict['client_ip']
                        client_id_value = callback_dict.get('client_id', '')
                        
                        # 广播消息：发送给所有客户端（除了发送者自己）
                        if client_id_value != client_id:
                            callback_dict['queue'].append(file_message)
                except Exception as e:
                    logger.error(f"将文件消息添加到客户端队列时出错: {e}")
        
        # 获取主机名用于日志记录
        current_hostname = socket.gethostname()
        logger.info(f"文件上传成功: {current_hostname} - {file.filename}")
        return jsonify({'success': True, 'transfer_id': transfer_id})
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        with lock:
            if transfer_id in active_transfers:
                active_transfers[transfer_id]['status'] = 'failed'
        return jsonify({'success': False, 'error': str(e)})

# 文件下载
@app.route('/api/download/<unique_filename>')
def download_file(unique_filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'error': '文件不存在'}), 404
    
    # 查找原始文件名
    original_filename = None
    for transfer in active_transfers.values():
        if transfer['unique_filename'] == unique_filename:
            original_filename = transfer['filename']
            break
    
    if not original_filename:
        # 如果找不到原始文件名，使用unique_filename
        original_filename = unique_filename.split('_', 1)[1] if '_' in unique_filename else unique_filename
    
    # 在Flask中，attachment_filename参数在新版本中已改为download_name
    response = send_file(file_path, as_attachment=True, download_name=original_filename)
    return response

# 获取活跃传输
@app.route('/api/transfers')
def get_transfers():
    # 清理过期的传输记录（超过24小时）
    current_time = datetime.now()
    for transfer_id, transfer_info in list(active_transfers.items()):
        # 确保传输记录有时间戳
        if 'timestamp' not in transfer_info:
            transfer_info['timestamp'] = datetime.now().isoformat()
        
        # 转换时间戳并比较
        try:
            transfer_time = datetime.fromisoformat(transfer_info['timestamp'])
            if (current_time - transfer_time).total_seconds() > 86400:
                del active_transfers[transfer_id]
        except (ValueError, TypeError):
            # 如果时间戳格式无效，使用当前时间作为默认值
            transfer_info['timestamp'] = datetime.now().isoformat()
    
    return jsonify(list(active_transfers.values()))

# 扫描局域网设备（实际扫描）
@app.route('/api/scan')
def scan_network():
    local_ip = get_local_ip()
    base_ip = '.'.join(local_ip.split('.')[:-1])
    found_devices = []
    
    # 实际扫描同一网段的IP
    import subprocess
    for i in range(1, 255):
        scan_ip = f"{base_ip}.{i}"
        if scan_ip != local_ip:
            try:
                # 使用ping命令检测设备是否在线
                param = '-n 1 -w 100' if os.name == 'nt' else '-c 1 -W 0.1'
                result = subprocess.run(f'ping {param} {scan_ip}', 
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                     shell=True, timeout=0.3)
                
                status = 'online' if result.returncode == 0 else 'offline'
                hostname = '未知'
                
                if status == 'online':
                    try:
                        hostname = socket.gethostbyaddr(scan_ip)[0]
                    except:
                        pass
                
                found_devices.append({
                    'ip': scan_ip,
                    'device_name': hostname,
                    'status': status
                })
                
                # 更新在线用户列表
                if status == 'online':
                    with lock:
                        online_users[scan_ip] = {
                            'device_name': hostname,
                            'ip': f"{scan_ip}:5000",  # 添加端口号
                            'last_seen': datetime.now()
                        }
            except Exception as e:
                found_devices.append({
                    'ip': scan_ip,
                    'device_name': '扫描错误',
                    'status': 'error'
                })
    
    return jsonify(found_devices)

# 清除历史消息
@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    global message_history
    with lock:
        # 首先删除所有相关的文件
        for msg in message_history:
            if msg.get('type') == 'file' and 'file' in msg and 'unique_filename' in msg['file']:
                unique_filename = msg['file']['unique_filename']
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"删除文件: {file_path}")
                except Exception as e:
                    logger.error(f"删除文件失败 {file_path}: {str(e)}")
        
        # 清空消息历史
        message_history = []
        # 清空历史文件
        try:
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
        except Exception as e:
            logger.error(f"删除历史文件失败: {str(e)}")
    
    logger.info("历史消息已清除，相关文件已删除")
    return jsonify({'success': True})

# 导出历史消息
@app.route('/api/export-history')
def export_history():
    with lock:
        history_copy = message_history.copy()
    
    return jsonify({
        'success': True,
        'history': history_copy
    })

# 处理favicon.ico请求，避免404错误
@app.route('/favicon.ico')
def favicon():
    # 返回空的favicon响应
    return '', 204

if __name__ == '__main__':
    # 获取本地IP地址
    ip = get_local_ip()
    print(f"服务器启动在 http://{ip}:5000")
    print(f"请在浏览器中访问 http://{ip}:5000 或 http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)