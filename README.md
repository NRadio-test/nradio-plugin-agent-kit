# NRadio Plugin Agent Kit

面向编码 Agent 的 **ultra 3.0 测试固件**插件开发规范、源码模板、APK 构建/验包工具。工具包版本 **3.0.0**，分支 **`3`**。

本分支只适配实测 `HC-WT9500 / 3.0.0.n0.c1-preview / OpenWrt 25.12-SNAPSHOT / kernel 6.12.94`。2.x（包括 max 2.3.3）仍使用 [main 分支](https://github.com/NRadio-test/nradio-plugin-agent-kit/tree/main)。本次不改动 main。

## Agent 入口

先读取 [AGENTS.md](AGENTS.md)。当前范围为插件制作、原生 APK 直接安装调试与官方本地接口兼容性检查；在线上架不在范围内。

**当前固件的关键边界**：系统包由 APK 管理，兼容 opkg 的数据库未登记这些包；旧 IPK 正常依赖预检失败。官方 appcenter 本地导入仍调用 opkg，已实测拒绝原生 APK（code=14）。不能把直接 LuCI 页面可用写成商店导入兼容。

- 元数据与模板：[example/plugin.json](example/plugin.json)、[example/](example/)
- 创建新项目：[tools/new-plugin.py](tools/new-plugin.py)
- APK 构建与主机验包：[tools/build-apk.py](tools/build-apk.py)、[tools/inspect-apk.py](tools/inspect-apk.py)
- 设备预检：[tools/preflight.sh](tools/preflight.sh)、[tools/device-dry-run-apk.sh](tools/device-dry-run-apk.sh)
- 回归检查：[tests/apk-regression.py](tests/apk-regression.py)、[tests/toolchain-regression.py](tests/toolchain-regression.py)
- 实测边界：[validation-result.json](validation-result.json)、[coverage-audit.json](coverage-audit.json)
- 测试固件反馈：[firmware-feedback.json](firmware-feedback.json)

## 最小工作流

要求 Python 3.10 或更新版本；这些工具仅依赖标准库。

```sh
python tools/new-plugin.py --id link-monitor --name "Link Monitor" --version 0.1.0 --output work/link-monitor
cd work/link-monitor
# 按实际任务实现 root/ 中的功能，再构建和验包。
python tools/build-apk.py
python tools/inspect-apk.py dist/luci-app-link-monitor-0.1.0-r1.apk --json-out dist/host-apk-inspection.json
```

该 helper 输出带逐文件校验的**无签名 APK v2 兼容包**，不是 APK v3/ADB 写入器。只支持纯脚本/资源；ELF、kmod、复杂依赖和生产签名用匹配厂商固件的 SDK。只在已审查源码、主机验包和摘要匹配时，为单次本地安装使用 `--allow-untrusted --no-network`，不改变全局信任或跳过依赖。

生成器提供默认关闭的最小心跳示例，不代表用户功能或完整升级状态策略已经实现。模板对关闭自启、手动停止等状态组合仍需产品改造，详见 AGENTS.md。

在仓库根目录复现本地工具检查：

```sh
python tests/toolchain-regression.py
python tests/apk-regression.py
```

## 证据范围

本地工具回归包括原有 24 项基础检查与新增 APK 检查，当前数量以 [apk-tool-validation.json](apk-tool-validation.json) 为准。旧 IPK 工具保留用于负向复现与载荷校验，不是本分支的默认部署路径。

[device-baseline.json](device-baseline.json) 记录当前单机环境。独立测试插件已执行原生 APK 安装、认证、CBI 保存、服务启停、版本升级、配置保留和卸载清理；[validation-result.json](validation-result.json) 逐项记录包摘要、通过/失败/未测边界。旧格式依赖检查与商店 APK 导入失败同样保留为证据。

测试结束后，测试插件已移除，系统 APK 数据库与测试前摘要相同，网络、DHCP、防火墙、无线和 fstab 摘要未变化。硬件扩容、刷机、SDK 原生编译、完整资源峰值与手机布局不属于此次插件验证。

本仓库不包含 SSH 凭据、令牌、配置备份或厂商二进制。示例与工具采用 [MIT License](LICENSE)。
