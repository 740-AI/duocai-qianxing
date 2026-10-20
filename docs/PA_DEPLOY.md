# PythonAnywhere 部署手册（图表版）

> 目标：拿到一个 `https://你的用户名.pythonanywhere.com` 的公网地址。
> 全程免费、不绑卡、国内可直连、实例不休眠、磁盘不丢失。

**总共 3 个环节，约 15 分钟。** 代码已托管在 GitHub，你不需要上传任何文件。

---

## 环节 1：注册账号（3 分钟）

打开 https://www.pythonanywhere.com/registration/register/beginner/

| 字段 | 填什么 |
|---|---|
| Username | 你的用户名，**全小写字母数字**，如 `duocaiqx`。这个会变成你的网址前缀，想好再填 |
| Email | 你的邮箱 |
| Password | 密码 |

点 **Register** → 进入新手引导页 → 一路点 **Next**（不用选付费套餐）→ 最后进到 **Dashboard**。

> ⚠️ 注册后如果要求邮箱验证，去邮箱点验证链接。

---

## 环节 2：拉代码 + 装依赖（5 分钟，复制粘贴一次搞定）

在 Dashboard 里找到 **New console here**，点它右边的 **Bash**。

黑色终端窗口出来后，**整段复制下面这一行**，粘贴进去回车：

```bash
curl -sL https://raw.githubusercontent.com/740-AI/duocai-qianxing/main/scripts/pa_setup.sh | bash
```

等 2–3 分钟，看到下面这行就成功了：

```
✅ 完成！项目位于 /home/你的用户名/duocai-qianxing
规划引擎自检通过： 7 个景点，预估 3246 元
```

> 如果提示 `git: command not found` 或下载失败，把终端里的报错截图发我。

---

## 环节 3：配置 Web 应用（5 分钟，3 处设置）

### 3.1 新建 Web 应用

Dashboard → 点 **Web** 标签 → 点 **Add a new web app** → 弹窗点 **Next** → 选 **Flask** → 选 **Python 3.10**（或列表里最新的 3.x）→ 点 **Next** 完成创建。

### 3.2 填三个路径

创建完会看到一个配置页，逐项修改：

| 配置项 | 填什么 |
|---|---|
| **Source code**（源码目录） | `/home/你的用户名/duocai-qianxing` |
| **Working directory**（工作目录） | `/home/你的用户名/duocai-qianxing` |
| **Virtualenv**（虚拟环境） | `/home/你的用户名/duocai-qianxing/.venv` |

> 把「你的用户名」换成你注册时填的（全小写）。

### 3.3 替换 WSGI 文件

在同一个配置页，找到 **Code** 区，点 **WSGI configuration file** 后面那个蓝色链接（形如 `/var/www/你的用户名_pythonanywhere_com_wsgi.py`）。

编辑器打开后：**全选（Ctrl+A）→ 删除 → 粘贴下面这段 → 改掉第一行用户名 → 点右上角 Save**：

```python
import sys, os

USERNAME = "把这里改成你的用户名"        # ← 只改这一处
PROJECT = f"/home/{USERNAME}/duocai-qianxing"

if PROJECT not in sys.path:
    sys.path.insert(0, os.path.join(PROJECT, "app"))
    sys.path.insert(0, PROJECT)

os.environ.setdefault("QX_DB", os.path.join(PROJECT, "data", "app.db"))

from server import app as _app, init_db
init_db()

application = _app
```

### 3.4 重载

回到 Web 配置页顶部，点绿色大按钮 **Reload**。

等 10 秒，点页面上方的网址：`https://你的用户名.pythonanywhere.com`

**看到"多彩黔行"首页 = 部署成功。**

---

## 上线后自检

| 检查 | 怎么做 | 期望 |
|---|---|---|
| 首页 | 打开网址 | 显示首页，样式正常（不是纯文字） |
| 规划 | 点"生成我的行程" | 2 秒内出现逐日时间轴 |
| 健康检查 | 访问 `/api/health` | 显示 `{"status":"ok","spots":25}` |
| 分享 | 点"生成分享链接" → 复制 → 新标签打开 | 直接显示行程 |
| 手机 | 手机浏览器打开 | 布局正常，无横向滚动 |

---

## 常见报错对照表

| 页面显示 | 原因 | 解决 |
|---|---|---|
| **Something went wrong**（通用错误） | 多数是 WSGI 路径或用户名写错 | 打开 Web → **Error log** 看最后 20 行；确认 `USERNAME` 和 `PROJECT` 路径没有多余空格 |
| `ModuleNotFoundError: No module named 'flask'` | Virtualenv 路径没填或填错 | Web 页面的 Virtualenv 必须填 `/home/用户名/duocai-qianxing/.venv` |
| 页面只有纯文字、没样式 | 静态文件没加载 | 检查是否访问的是 `https://` 而不是 `http://`；强刷（Ctrl+F5） |
| `no such file or directory: .../app.db` | data 目录权限 | 在 Bash 里执行 `mkdir -p ~/duocai-qianxing/data` |
| Reload 后仍是旧版本 | 没点 Reload 或缓存 | 再点一次 Reload，浏览器 Ctrl+F5 |
| 502 / 一直转圈 | 应用启动崩溃 | 看 Error log，把最后 10 行发我 |

---

## 日常维护（可选）

**改代码后如何更新**：Bash 控制台执行

```bash
cd ~/duocai-qianxing && git pull && source .venv/bin/activate && pip install -q -r requirements.txt
```
然后回 Web 页面点 **Reload**。

**备份数据**（分享的行程存在 `data/app.db`）：

```bash
cp ~/duocai-qianxing/data/app.db ~/backup-$(date +%m%d).db
```

**免费版限制**：
- 每 3 个月需要在网页上点一次「Run until 3 months from today」续期（不点会暂停，点一下即恢复）；
- 单日 CPU 时间有限，但本应用是静态数据 + 轻量计算，正常访问远达不到上限。

---

## 已在本地完成的等价性验证

用与 PythonAnywhere 相同的"虚拟环境 + 原生 WSGI"方式实测：

| 项目 | 结果 |
|---|---|
| venv 创建 + `pip install -r requirements.txt` | ✅ 成功 |
| `/api/health` | ✅ 200 `{"status":"ok"}` |
| 首页渲染 | ✅ 200，9590 字节 |
| `/api/plan` | ✅ 200，7 个景点，3246 元 |
| 分享页路由 | ✅ 200 |
| WSGI 模板语法 | ✅ 通过 AST 校验 |

> 也就是说，剩下的只是"在平台上把三个路径填对"，逻辑层面不会出问题。
