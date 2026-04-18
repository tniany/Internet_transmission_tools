<center><h1>浅月不息 - 局域网互传工具</h1></center>

[![Stars](https://count.getloli.com/@tniay-flad-2?name=tniay-flad-2\&theme=asoul\&padding=7\&offset=0\&align=top\&scale=1\&pixelated=1\&darkmode=auto)](https://github.com/tniay-flad-2)

<br />

![GitHub stars](https://img.shields.io/github/stars/你的用户名/浅月不息-局域网互传?style=social)
![GitHub forks](https://img.shields.io/github/forks/你的用户名/浅月不息-局域网互传?style=social)
![GitHub issues](https://img.shields.io/github/issues/你的用户名/浅月不息-局域网互传)
![GitHub license](https://img.shields.io/github/license/你的用户名/浅月不息-局域网互传)

<p>一个简单高效的局域网文件传输工具，支持所有格式文件的上传下载，无大小限制，并提供实时进度显示。</p>

<br />

## 功能特点

- 📁 **文件传输**：支持所有格式文件，无大小限制
- 💬 **文字消息**：支持局域网内文字聊天
- 📊 **实时进度**：显示文件上传下载进度和速度
- 🌐 **局域网检测**：自动检测局域网内在线设备
- 🖥️ **跨平台**：支持Windows、Mac、Linux等所有支持Python的系统
- 🎨 **现代化界面**：简洁美观的Web界面

## 技术栈

- **后端**：Python + Flask
- **前端**：HTML5 + JavaScript + CSS3
- **依赖**：flask, flask-cors

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python main.py
```

### 3. 访问应用

服务启动后，会显示本地访问地址：

- 在浏览器中访问 `http://localhost:5000` （本机访问）
- 在同一局域网内的其他设备上访问 `http://[服务器IP]:5000` （如 `http://192.168.1.100:5000`）

## 使用说明

### 文件传输

1. **上传文件**：点击或拖拽文件到上传区域，支持多文件同时上传
2. **下载文件**：点击其他用户发送的文件消息中的下载按钮
3. **传输进度**：在界面底部实时显示文件传输进度和速度

### 文字聊天

1. 在底部输入框中输入文字消息
2. 按Enter键或点击发送按钮发送消息
3. 消息会实时显示在聊天区域

### 设备发现

- 系统会自动检测并显示局域网内的其他在线设备
- 点击左侧边栏可以查看所有在线用户

## 注意事项

1. 确保所有设备在同一局域网内
2. 防火墙设置可能需要允许5000端口的访问
3. 对于超大文件传输，建议使用稳定的局域网连接
4. 文件默认保存在`uploads`文件夹中，请确保有足够的磁盘空间

## 常见问题

### 其他设备无法访问服务？

- 检查防火墙设置，确保5000端口已开放
- 确认所有设备在同一局域网内
- 尝试使用IP地址而不是主机名访问

### 文件传输速度慢？

- 检查网络连接质量
- 避免在传输大文件时进行其他网络密集型操作
- 确保局域网路由器性能良好

### 服务启动失败？

- 检查Python版本是否兼容（推荐Python 3.6+）
- 确保所有依赖已正确安装
- 检查5000端口是否被其他程序占用

## 许可证

MIT License

## 更新日志

### v1.0.0

- 初始版本发布
- 支持文件上传下载
- 支持文字消息
- 实时进度显示
- 局域网设备检测

## Stargazers over time

[![Star History Chart](https://api.star-history.com/svg?repos=tniay-flad-2/浅月不息-局域网互传\&type=Date)](https://star-history.com/#tniay-flad-2/浅月不息-局域网互传\&Date)
