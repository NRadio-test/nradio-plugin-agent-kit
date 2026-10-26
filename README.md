# NRadio Plugin Agent Kit

面向编码 Agent 的 NRadio ultra / max 插件制作规范、源码模板和本地构建工具。当前版本 **v1.3**。

## Agent 入口

先读取 [AGENTS.md](AGENTS.md)。当前任务范围是插件制作、IPK 构建与本地安装调试，保留官方固件 LuCI 和 appcenter 本地接入契约；官方应用商店在线上架不在当前范围。

- 元数据与模板：[example/plugin.json](example/plugin.json)、[example/](example/)
- 创建新项目：[tools/new-plugin.py](tools/new-plugin.py)
- 构建与主机验包：[tools/build.py](tools/build.py)、[tools/inspect-ipk.py](tools/inspect-ipk.py)
- 设备预检：[tools/preflight.sh](tools/preflight.sh)、[tools/device-dry-run.sh](tools/device-dry-run.sh)
- 回归检查：[tests/toolchain-regression.py](tests/toolchain-regression.py)
- 实测边界：[validation-result.json](validation-result.json)、[coverage-audit.json](coverage-audit.json)

## 最小工作流

要求 Python 3.10 或更新版本；这些工具仅依赖标准库。

```sh
python tools/new-plugin.py --id link-monitor --name "Link Monitor" --version 0.1.0 --output work/link-monitor
cd work/link-monitor
# 按实际任务实现 root/ 中的功能，再构建和验包。
python tools/build.py
python tools/inspect-ipk.py dist/luci-app-link-monitor_0.1.0-1_all.ipk --json-out dist/host-inspection.json
```

生成器提供默认关闭的最小心跳示例，不代表用户功能或产品升级策略已经实现。原生源码编译、运行时 ABI 和具体插件真机功能需要相应工具链及验证。

在仓库根目录复现本地工具检查：

```sh
python tests/toolchain-regression.py
```

## 证据范围

本地构建与验包有 24 项回归检查。随附基线 IPK 的摘要与此前在两台样机上完成语法检查和 opkg noaction 的包一致；真实插件安装、页面、服务及 appcenter 本地导入结果按 JSON 记录中的 pass / fail / not_run 判断。

[device-baseline.json](device-baseline.json) 保留固件与实现基线。[max-extroot-result.json](max-extroot-result.json) 记录其中一台 max 启用 64GB TF extroot 的结果；这不代表所有 max 都有相同存储配置。

本仓库不包含 SSH 凭据、令牌、配置备份或厂商二进制。示例与工具采用 [MIT License](LICENSE)。
