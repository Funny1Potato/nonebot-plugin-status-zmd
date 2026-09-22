# 更新日志

版本用 git tag（`vX.Y.Z`）标记，未发布到 PyPI。

## v0.1.0

首个版本。

- 终末地风格状态图：电量环（含径向条纹、粒子点云、双装饰弧）、应用概况、终端链路、
  设备性能走势、设备信息、底栏
- 三种版式（`full` / `gauge` / `perf`）与板块级开关，设备性能区支持逐设备开关
  （`STZMD_DEVICES`：`cpu` / `mem` / `disk` / `net`，列表顺序即图上顺序）
- `psutil` 跨平台采集：CPU、内存/Swap、磁盘容量与读写、网络速率、进程列表
  - CPU 占用自己用 `cpu_times` 差值计算，并在启动时建立基准，首张图即有真实值
  - 启动期采集有超时预算（`STZMD_COLLECT_TIMEOUT`），慢 I/O 不会拖住机器人启动
- 常驻周期采样 + 历史窗口，走势图按窗口渲染
- NoneBot 自身状态：运行时长、Bot 连接时长、收发计数、Bot 列表与头像
- `nonebot-plugin-htmlrender` 0.6 / 0.7 / 0.8+ 三版本兼容层
- 支持 nonebot2 2.3.0 及以上：2.3 上会解析到 `alconna 0.59` / `uninfo 0.6` /
  `htmlrender 0.6.3`（这三个依赖自某个版本起要求 nonebot2 >= 2.5.0），
  已用 2.3.0 那一套依赖跑通全部测试与出图
- 缓存走 `nonebot-plugin-localstore`（Bot 头像、渲染失败的 HTML）
- `tools/preview.py` 预览工具：不启动机器人即可出 HTML / PNG