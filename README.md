# 墨墨今日未记住

把墨墨背单词里今天已经学过、但没有标成「认识」的词，连同墨墨官方释义，贴到屏幕右下角。

每天 10:05 自动跑一次。也可以在 Raycast 里搜「墨墨今日未记住」手动贴。

## 它做什么

1. 用墨墨开放 API 取今天已学完的词，去掉 `FAMILIAR`（认识）。
2. 用本地词库把拼写对上墨墨词条，再读公开接口里的「官方 / 核心释义」。
3. 画一张 0.75 倍的卡片，只有单词和释义。
4. 交给正在运行的 PixPin，贴在屏幕右下角。

手动只看列表、不贴图：

```bash
python3 fetch_today.py
```

## 准备

- macOS，已安装 [PixPin](https://pixpinapp.com)，并且系统设置里允许它录制屏幕、使用辅助功能。
- 能 `import AppKit, Quartz` 的 Python。没有的话：

```bash
pip3 install pyobjc-framework-Cocoa pyobjc-framework-Quartz
```

- 墨墨开放 API token。在 App 里打开「我的 → 更多设置 → 实验功能 → 开放 API」，或浏览器打开：

https://open.maimemo.com/open/api/v1/tokens/openapi

登录后把 token 存成仓库根目录的 `.token`（一行，不要提交）。也可以用环境变量 `MAIMEMO_TOKEN`。网页 token 大约 7 天过期。

- 词库 `data/maimemo.v3.db`。这是墨墨安装包里的 `assets/maimemo.v3.db`，用来把拼写换成词条 id。公开释义接口要这个 id。把文件放到 `data/maimemo.v3.db`。`unpacked/assets/maimemo.v3.db` 也会被认作同一份词库。词库、token、安装包都不要提交。

## 安装

在仓库根目录执行：

```bash
chmod +x install.sh
./install.sh
```

脚本会：

- 找到带 PyObjC 的 Python。
- 安装 `~/Library/LaunchAgents/com.momo.today-pin.plist`，每天 10:05 跑 `pin_today.py`。
- 如果 `~/Documents/commands` 存在（或你设置了 `RAYCAST_SCRIPTS`），写入 Raycast Script Command。Raycast 需要把这个目录加在 Settings → Extensions → Script Commands 里。

日志写在 `pin-today.log`。

## 手动运行

```bash
python3 pin_today.py
```

成功时打印 `已贴上 N 个词`。今天还没学，或剩下的都是「认识」，会收掉右下角那张卡片并打印「今天没有未记住的词」。

## 文件

| 文件 | 作用 |
| --- | --- |
| `pin_today.py` | 取词、画卡片、贴到右下角 |
| `fetch_today.py` | 只打印今天已学的词 |
| `install.sh` | 安装定时任务和 Raycast 命令 |
| `launchd/com.momo.today-pin.plist` | 定时任务模板，`@PYTHON@` 和 `@ROOT@` 由安装脚本替换 |
| `raycast/momo-today-pin.sh` | Raycast 命令模板 |

生成的卡片、释义缓存、日志和 `.token` 都在 `.gitignore` 里。
