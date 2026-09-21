<!-- markdownlint-disable MD033 MD041 -->

<div align="center">

# NoneBot-Plugin-Status-ZMD

_✨ 以《明日方舟：终末地》电量系统风格展示服务器运行状态的 NoneBot2 插件 ✨_

</div>

## 📖 介绍

发一条指令，得到一张终末地风格的设备状态图：圆形电量环 + 设备性能走势 + 应用概况 +
终端链路，全部数据来自 `psutil` 跨平台采集。

视觉规范移植自 [zmd-manager](https://github.com/Funny1Potato) 的
`frontend/index.html`：浅暖灰底 `#ececeb` + 18px 径向点阵、深炭数据块、亮黄电量环
`#ffe23d`、左右装饰弧、右下切角的图标方块、黄柱走势图。

与原版的两处必要差异（原版是 Tauri 里跑 JS 的实时界面，这里是静态出图）：

- **粒子点云**：原版是 `requestAnimationFrame` 每帧重绘的 canvas，改成服务端按固定
  种子生成的静态 SVG 点云（同一份输入永远出同一张图）。
- **走势柱**：原版是 canvas 绘制且页面隐藏时画空，改成服务端输出的 CSS 柱条。

## 💿 安装

```bash
nb plugin install nonebot-plugin-status-zmd
# 或
uv add nonebot-plugin-status-zmd
# 或
pip install nonebot-plugin-status-zmd
```

### ⚠️ 渲染后端（nonebot-plugin-htmlrender）

插件通过 `nonebot-plugin-htmlrender` 拿浏览器页面，**0.6 / 0.7 / 0.8+ 都支持**，
但 0.8 起它不再内置浏览器后端，需要额外两步：

```bash
# htmlrender >= 0.8：装 Playwright extra
pip install "nonebot-plugin-htmlrender[playwright]>=0.8"
# 或直接装本插件提供的配套 extra（等价）
pip install "nonebot-plugin-status-zmd[htmlrender8]"

# 任一版本都需要浏览器内核
playwright install chromium
# Debian/Ubuntu、容器、CI 建议带上系统依赖
playwright install --with-deps chromium
```

```properties
# htmlrender >= 0.8 还需要在 .env 里选择 Provider
RENDER={"provider":"playwright","startup":"warmup"}
```

> **国内网络**：Chromium 内核走 `cdn.playwright.dev` / `storage.googleapis.com`，
> 直连容易超时。加一个镜像环境变量即可，命令本身不用改：
>
> ```bash
> # Windows (cmd)
> set "PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright"
> # Linux / macOS
> export PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
> ```
>
> 另外 htmlrender 0.7 起把浏览器目录搬到了 localstore 数据目录（首次启动的日志里
> 会打印具体路径）。如果出图报 `Executable doesn't exist`，把
> `PLAYWRIGHT_BROWSERS_PATH` 指到那个目录再装一次即可，例如：
>
> ```bash
> set "PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\nonebot2\nonebot_plugin_htmlrender"
> playwright install chromium
> ```

各版本走的内部分支（插件启动时会打印实际走哪条）：

| htmlrender | 取页面方式 | 备注 |
| --- | --- | --- |
| 0.6.x | `get_new_page()` | 浏览器是包内依赖，无需额外配置 |
| 0.7.x | `get_render_context()` | 不走 `get_new_page()`，因为它已被标 `@deprecated` |
| 0.8+ | `get_default_application().extensions.playwright.browser()` | 需要 `[playwright]` extra + `render.provider` |

如果后端不可用，插件**不会**在启动时报错退出，而是打印一条带完整修复步骤的告警，
并在指令触发时把同样的提示发给使用者。

## 🎉 使用

```text
status
系统状态
```

指令名可用 `STZMD_COMMAND` 修改。默认**仅 SUPERUSER**可用（状态图含主机名、IP、
进程、磁盘等信息，不适合公开）。

> NoneBot 默认只把 `/` 开头的消息当命令，想直接发 `status` 触发，需要把空字符串
> 加进 `COMMAND_START`：
>
> ```properties
> COMMAND_START=["", "/"]
> ```

## ⚙️ 配置

### 见 [.env.example](.env.example)

常用几项：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `STZMD_LAYOUT` | `full` | `full` 综合长图 / `gauge` 只出电量环 / `perf` 只出设备性能 |
| `STZMD_BLOCKS` | 全部 | 板块开关：`header` `gauge` `apps` `bots` `perf` `specs` `footer` |
| `STZMD_DEVICES` | `cpu mem disk net` | 设备性能区逐设备开关，列表顺序即图上顺序 |
| `STZMD_ONLY_SUPERUSER` | `true` | 是否仅 SUPERUSER 可用 |
| `STZMD_COLLECT_INTERVAL` | `5` | 后台采样间隔（秒） |
| `STZMD_HISTORY_SIZE` | `180` | 走势图保留的采样点数（窗口 = 间隔 × 点数） |
| `STZMD_COLLECT_TIMEOUT` | `15` | 单次采集等待上限（秒），超时先继续、不拖住启动 |
| `STZMD_GAUGE_VALUE_MAX` | `325799` | 电量环分母（终末地的游戏口径） |
| `STZMD_FONT_FAMILY` | 空 | 指定 CSS 字体栈，例如 `"Noto Sans CJK SC"` |
| `STZMD_FONT_PATH` | 空 | 指定字体文件并内联进图片（≤ 8MB），保证字形一致 |

### 版式与板块的关系

`STZMD_LAYOUT` 决定整体容器结构，`STZMD_BLOCKS` 决定渲染哪些板块，只有两者都允许的
板块才会出现：

| 版式 | 允许的板块 |
| --- | --- |
| `full` | 全部：顶栏 +（电量环 \| 应用概况+终端链路）+ 设备性能 + 设备信息 + 底栏 |
| `gauge` | 顶栏 + 电量环 + 终端链路 + 设备信息 + 底栏 |
| `perf` | 顶栏 + 设备性能 + 终端链路 + 设备信息 + 底栏 |

`STZMD_DEVICES` 进一步控制设备性能区里出哪几行（可只留 `["cpu", "mem"]` 做轻量监控，
或 `["net"]` 只看网络）：

| 取值 | 对应行 |
| --- | --- |
| `cpu` | 处理器（占用 / 频率 / 最高频率） |
| `mem` | 内存（占用 / Swap / 总容量） |
| `disk` | 每个分区一行（容量占用 / 读写 / 文件系统），受 `STZMD_IGNORE_PARTS` 过滤 |
| `net` | 每张网卡一行（下行 / 上行 / 链路），受 `STZMD_IGNORE_NETS` 过滤 |

### 启动期采集超时

宿主机的挂载点失联时 `psutil.disk_usage()` 这类调用可能阻塞很久。启动期（静态信息 +
基准 + 首采）**共用一份** `STZMD_COLLECT_TIMEOUT` 总预算：超时**不会**中断采集，
只是先放行——机器人照常启动，数据由下个采样周期补上；若出图时仍没有数据，会直接回
一句「状态数据还没准备好」而不是卡住。超时期间后续采样会被跳过（不排队），避免卡顿
扩散。迟到的采集完成后依然会把数据写进状态。

## 🎨 数据来源与口径

- **采集**：全部走 `psutil`，跨平台；所有阻塞调用都丢进线程池，不卡事件循环。
- **不含 GPU**：显卡指标跨平台差异太大，本插件不采集；设备性能区只有
  处理器 / 内存 / 磁盘 / 网络 四类，可用 `STZMD_DEVICES` 各自开关。
- **电量环**：`综合占用 = CPU × STZMD_GAUGE_CPU_WEIGHT + 内存 × STZMD_GAUGE_MEM_WEIGHT`，
  映射到 `0-360°` 扫角；中间大数字 = `综合占用 / 100 × STZMD_GAUGE_VALUE_MAX`（游戏口径），
  「实际占用」为当前值，「最大占用」为历史窗口内的峰值。
- **走势柱**：处理器/内存/磁盘容量按百分比，网络按链路占用百分比（拿不到链路速率时
  按窗口内峰值归一）。
- **磁盘读写**：`psutil` 的物理盘计数器差分。单物理盘机器上所有分区共用同一份速率；
  多盘且无法对应到物理盘时显示 `—`（不猜）。
- **进程列表**：只按 `STZMD_IGNORE_PROCS` 和 pid 过滤，不做「占用太小就丢弃」的过滤，
  排序后取前 `STZMD_PROC_LEN` 个；CPU 默认折算成整机占比（`STZMD_PROC_CPU_MAX_100P=true`
  可改成单核口径）。
- **磁盘型号**：Linux 读 `/sys/block/*/device/model`；Windows/macOS 拿不到（不引入
  WMI），显示 `—`。
- **网络地址**：只列 `10./192./172./100.` 段的地址，最多 3 条；`169.254` 这类自动
  获取失败的地址不显示。
- **CPU 占用**：自己用 `psutil.cpu_times()` 差值算，不用 `psutil.cpu_percent()`——
  后者的基准是进程级全局变量，其它插件调用一次就会把基准吃掉，且首个返回值按文档
  本身就是「无意义的 0.0」。插件启动时会先建立基准，所以第一张图就有真实占用率。
- **缓存**：Bot 头像与渲染失败时的 HTML 落在
  [nonebot-plugin-localstore](https://github.com/nonebot/plugin-localstore) 的缓存目录
  （`<localstore cache>/nonebot_plugin_status_zmd`），头像 7 天后过期重取；
  测试与 `tools/preview.py` 不在插件加载上下文里，这时退回系统临时目录。
- **收发计数**：接收用事件 hook；发送优先按各适配器的发消息 API 名计数。
  拿不到时显示「未知」，不会假装是 0。

## 🛠️ 开发

```bash
pip install -e ".[htmlrender8,dev]"

# 不启动机器人也能看效果（输出 HTML，不需要浏览器）
python tools/preview.py --demo --open
# 三种版式各出一份 + 出图
python tools/preview.py --all --shot
# 真实采集数据
python tools/preview.py --live --shot

ruff check . && ruff format --check . && pytest
```

`--demo` 走的是与线上完全相同的组装 / 渲染代码，只把采集结果换成固定种子假数据，
所以预览页里调好的样式线上表现一致。

## 📝 版本管理

未发布到 PyPI：版本号在 `nonebot_plugin_status_zmd/__init__.py` 的 `__version__`
里，用 git tag（`vX.Y.Z`）标记，变更记在 [CHANGELOG.md](CHANGELOG.md)。

## 💡 鸣谢

- [nonebot-plugin-picstatus](https://github.com/lgc-NB2Dev/nonebot-plugin-picstatus)
  —— 采集器组织方式、渲染管线与「指令带图」的整体思路参考
- [zmd-manager](https://github.com/Funny1Potato) —— 终末地风格的视觉规范来源
- [nonebot-plugin-htmlrender](https://github.com/kexue-z/nonebot-plugin-htmlrender)
  —— HTML 渲染后端

## 📄 许可

MIT