# ultra 3.0 APK 插件开发细则（供 Agent 执行）

规范版本：3.0.1。更新日期：2026-10-27。与 [AGENTS.md](AGENTS.md) 一起使用。

## 1. 已确定的方向与未确定的细节

用户转述技术反馈：**3.0 后续按 APK 开发。新插件的交付物为 `.apk`，整个包生命周期统一由 APK 管理。**不要再让用户选择 IPK/APK，也不要为了继续开发而制作空依赖 IPK、改后缀或补写 opkg 安装记录。

| 项目 | Agent 应采用的事实 |
| --- | --- |
| 新插件格式与依赖管理 | 已确定为 APK |
| 正式构建 | 优先采用匹配厂商固件的 APK SDK；原生程序、内核模块必须使用匹配 SDK |
| 最终 APK 格式版本、SDK 发布号、签名与信任规则 | 尚未取得并验证，不能凭“采用 APK”推断 |
| 当前脚本调试工具 | `build-apk.py` 输出无签名 APK v2 兼容包，仅纯脚本/资源 |
| 已有设备证据 | 仅 ultra / HC-WT9500 / 3.0.0.n0.c1-preview |
| 未来固件和官方商店 | 需要重新验证；方向确认不等于已经完成实现 |
| max 与 2.x | 不在本分支适配范围；旧版指南在 main |

`apk-tools 3.0.5` 是包管理工具版本，不是对最终包格式的承诺。当前 helper 已验证 v2 兼容包可直接调试；SDK 产出的 v3/ADB 包应使用 SDK/原生工具检验，不能因本仓库 v2 inspector 拒绝就认定为坏包。[APK 元数据规范同时区分 v2 与 v3 字段](https://github.com/alpinelinux/apk-tools/blob/v3.0.5/doc/apk-package.5.scd)。

## 2. 先记录目标，再选构建路径

先运行 `tools/preflight.sh`，记录型号、完整固件版本、内核、APK 版本、包实际架构、LuCI 实现、存储和目标路径归属。核对真实设备身份；不拿同 board_name 或 ARM64 作为跨型号兼容证明。

在任务记录中填写：

```text
model / firmware / kernel:
apk-tools version / installed package architecture:
build method: matching_vendor_sdk | local_apkv2_helper
SDK release / source commit / toolchain: 未取得则 null
artifact format / architecture / signature:
LuCI implementation and route:
required runtime features:
device validation status and evidence:
```

缺少 SDK 时继续完成业务源码、Lua 页面、服务、配置和静态检查；仅纯脚本/资源可以用本地 helper 做原型。未能编译的原生部分记 `not_run` 并说明具体缺项，不下载通用二进制冒充适配。

## 3. 依赖由 APK 正常求解

按实际运行需要声明直接依赖，保留真实约束。读取目标 APK 安装记录中的包名、版本、架构；不要沿用旧 IPK 或桌面 Alpine 的包名猜测厂商组件。

```sh
# 示例查询，不修改安装状态；最终依赖闭包由目标 APK 求解器验证。
apk --no-network info --exists libc luci-base
apk --no-network info --who-owns /usr/lib/lua/luci/dispatcher.lua
```

必要时从 `/lib/apk/db/installed` 读取 P:/V:/A: 字段，只读，不手工修改。当前 `apk info -v` 的输出不能直接当作版本列表；`opkg status` 和 `opkg list-installed` 不能作为 APK 组件是否存在的判据。

helper 的项目元数据示例：

```json
{
  "depends": ["libc", "luci-base"]
}
```

这只是示例。实际使用 `curl`、`jsonfilter`、jshn、锁工具或其他程序时，应查询其 APK 提供者并声明必要依赖；不能因为样机已经预装就省略。helper 只接受简单包名，版本表达式、虚拟 provides 和复杂依赖交给匹配 SDK；不要删除这些约束来迁就 helper。

缺少依赖时保留求解错误，定位是缺包、版本/ABI、架构、缓存、签名还是仓库不匹配。只补充来自已确认匹配仓库的必要依赖，先审核模拟安装计划；不执行整机 `apk upgrade` 来试错，不覆盖基础库、不清空 world、不忽略依赖。

APK 用原生元数据描述依赖并进行求解；[APK 包元数据](https://github.com/alpinelinux/apk-tools/blob/v3.0.5/doc/apk-package.5.scd)和[本地文件安装约束](https://github.com/alpinelinux/apk-tools/blob/v3.0.5/doc/apk-add.8.scd)可用于理解行为，厂商实际包名和依赖仓库仍以目标环境为准。

## 4. 构建路径

### 4.1 匹配厂商 APK SDK：正式构建路径

取得 SDK 后核对：固件对应发布号/源码提交、目标架构、musl 与库 ABI、内核 ABI、APK 打包后端、依赖 feeds、密钥与信任流程。SDK 记录保留到交付清单；私钥不进入源码或公共仓库。

将业务代码整理为 OpenWrt 包配方，声明依赖、配置保护、安装目录与生命周期。仓库 `example/Makefile` 和生成工程的 `Makefile` 是迁移草稿：`Build/Compile` 为空，旧维护脚本含 `IPKG_INSTROOT`。不能直接据此声称已完成厂商 APK SDK 支持。

常规 OpenWrt SDK 构建入口示意如下，实际命令和包选择以厂商 SDK 为准，当前没有执行证据：

```sh
# 在匹配 SDK 中，先按该 SDK 文档接入并选中软件包，再编译。
make package/luci-app-link-monitor/compile V=s
```

检查产物确实为目标 SDK 生成的 APK；仍输出 IPK 时，重新核对 SDK/backend，不改文件后缀。审核最终包的架构、依赖、配置保护规则、脚本事件和目录清单，不直接信任 Makefile 的表面字段。

上游 [OpenWrt 包装实现](https://github.com/openwrt/openwrt/blob/main/include/package-pack.mk)显示 APK/IPK 后端及生命周期包装具有差异；这是实现参考，不代表此处主线代码与厂商 SDK 完全一致。

### 4.2 纯脚本原型：本地 APK v2 helper

主机 Python 3.10+，仅标准库：

```sh
python tools/new-plugin.py --id link-monitor --name "Link Monitor" --version 0.1.0 --output work/link-monitor
cd work/link-monitor
# 实现 root/、control/ 与 plugin.json，再构建。
python tools/build-apk.py
python tools/inspect-apk.py dist/luci-app-link-monitor-0.1.0-r1.apk --json-out dist/host-apk-inspection.json
```

生成器复制本细则、AGENTS.md 与 distribution-policy.json，下一位 Agent 继续按 APK 开发。

此路径只支持普通目录和纯 Shell/Lua/UI/资源。源码 `plugin.json` 的 `architecture: all` 是共享源码工具的内部输入；最终 APK 必须读取 `.PKGINFO`，helper 输出为 `noarch`。不要把 all 写入 APK 来沿用 IPK 规则，也不要把 ELF 标成 noarch。

版本由 `version` 与正整数 `release` 生成，例如 `0.1.0-r1`。源码或打包内容变化就递增版本/发布号，保留旧包与校验值。不要让同一个版本对应多份无法区分的文件。

载荷包含必要父目录，执行文件 0755、普通资源通常 0644，脚本使用 LF；不夹带其他插件文件。helper 保留二进制资源字节、记录 datahash 和逐文件校验，但没有生产签名能力。SHA256SUMS 是一致性记录，不是发布者身份认证。

`build.py` 与 IPK 工具仅用于历史复现和 helper 内部校验，不作为新插件的发布命令。SDK 产物、用户第三方 APK 与 helper 格式不符时，先辨认格式和信任来源，不直接解包执行。

## 5. APK 包、LuCI 页面与业务核心分别验收

打包格式改为 APK 不会自动升级厂商 LuCI。当前样机采用传统 Lua controller + CBI/HTM，插件页面放在 `nradioadv/system/<id>`。不要只提供 `menu.d` 和现代 JS view；先确认 `view.js`、`rpc.js`、`ui.js`、`poll.js` 等模块和 dispatcher 路由机制实际存在。

真实安装后检查：

- 所有载荷文件、父目录、权限及 APK 文件归属与清单一致；不能只看“已安装”记录或命令返回 0。
- 主 controller、配置守卫、CBI/HTM 均到位，直接路由可登录访问；HTTP 200 不是内容正确的充分证据。
- 后端参数校验、认证与写操作保护符合现有固件；无 Shell 字符串拼接注入。
- 任务启动前检查 job 可执行且具备资源条件；分别记录启动接受、任务完成和业务成功，不能把 `ok=true` 的排队响应当成执行通过。
- 状态显示系统实际使用的 APK 与真实组件版本，不因为兼容 opkg 命令存在就误报系统仍用 IPK。

如插件另装代理或下载原生核心，管理器可用和核心可用分别记录。按业务需要检查 BTF、具体内核配置、模块、设备节点和运行探针；版本号足够不表示功能齐全。普通 Lua/UI 插件不要求这些无关能力。核心尚不可运行时，管理页应显示具体原因，并禁止会失败的操作。

## 6. 生命周期与用户配置

包只拥有自身的 UCI、服务、程序、状态目录和页面。保持包名、服务名、UCI 名称及路由在升级中稳定。

| 事件 | 必须满足的要求 |
| --- | --- |
| 首次安装 | 初始化必要默认配置，默认功能状态符合产品约定；不覆盖用户已有同名配置 |
| 升级 | 保留用户配置及关闭状态；必要迁移可重复执行，失败可识别 |
| 服务 | 使用 procd；区分 UCI enabled、开机自启、进程当前运行三个状态 |
| 卸载 | 停止自身进程，释放端口和开机项；按明确政策保留或清理自身配置 |
| 失败恢复 | 保留日志、包状态和原版 APK；按已验证方案恢复，不擅自清理共享依赖 |

当前 helper 把 preinst/postinst 映射为 APK 安装与升级事件，prerm/postrm 映射为卸载事件；这不是厂商 SDK 全部包装机制。SDK 的镜像构建根、脚本参数和环境需逐项确认，不能只检测旧 `IPKG_INSTROOT` 就认为覆盖完整。

模板 postinst 会 enable/restart，未实现所有关闭态/手动停止态升级策略。产品化前应按上述表格改造并测试，不把示例的成功路径当作生命周期认证。

用户修改后的配置遇到新默认配置时，当前样机已观察到 `.apk-new`；应按保护规则迁移/合并，不覆盖用户配置来消除它。SDK 保护路径与 conffiles 生成方式须检查实际产物。

## 7. 设备预检、安装和核验

先确认目标文件没有被其他包占有，记录本插件原状态及配置、旧 APK 和摘要。安装计划必须限定在任务范围；模拟计划如涉及替换系统基础组件，先解决依赖或 SDK 不匹配问题。

对本仓库可信 helper 构建的无签名包，按 manifest 中本次 SHA256 上传并预检：

```sh
# 开发机：在生成工程根目录执行，凭据由执行环境提供。
scp -O dist/luci-app-link-monitor-0.1.0-r1.apk root@<device>:/tmp/
scp -O tools/device-dry-run-apk.sh tools/syntax-check.lua root@<device>:/tmp/

# 设备：替换 EXPECTED_SHA256 为本次实际摘要；脚本绑定已验证预览固件。
sh /tmp/device-dry-run-apk.sh /tmp/luci-app-link-monitor-0.1.0-r1.apk /tmp/syntax-check.lua EXPECTED_SHA256
apk --allow-untrusted --no-network add /tmp/luci-app-link-monitor-0.1.0-r1.apk
apk --no-network info --exists luci-app-link-monitor
apk --no-network info --who-owns /usr/lib/lua/luci/controller/nradio_adv/link_monitor.lua
```

预检不运行 hook，不安装依赖，检查前后数据库/world 一致。脚本限于已过主机检查、摘要匹配的 helper 包；不能用它处理任意来源的 APK。新固件触发版本守卫时先复核格式和命令，不为了通过而直接删守卫。

正式签名包应通过厂商受支持的信任方式验证，安装命令中不需要开发用 `--allow-untrusted`：

```sh
# 本地包及必要依赖已备齐时使用离线模式；审核模拟计划后再安装。
apk verify /tmp/<package>.apk
apk --no-network --simulate --no-scripts add /tmp/<package>.apk
apk --no-network add /tmp/<package>.apk
```

签名未知时先取得厂商信任规则；不把开发用绕过签名参数写成正式发布要求。签名通过也不能替代 ABI、依赖和业务测试。

安装后对照 manifest 核验全部文件及归属，再测试认证、输入边界、配置保存、服务启停和日志。接口返回成功但文件缺失或 job 不可执行时，记录真实失败，不继续宣称可用。

升级与卸载先模拟，再执行当前插件的目标动作；helper 无签名包仅在该次安装命令上加开发用信任选项：

```sh
apk --no-network --simulate add /tmp/<new-version>.apk
apk --no-network add /tmp/<new-version>.apk
apk --no-network --simulate del <package-name>
apk --no-network del <package-name>
```

上例是不同操作的命令格式，不要求在每次任务里连续升级并卸载用户已有插件。不要调用 `opkg remove` 清理 APK 包。遇到超时先查询真实状态，不重复安装，不删除系统锁。

## 8. 商店接入与交付边界

保留 `/cgi-bin/luci/nradioadv/system/appcenter` 的适配目标与独立 LuCI 主入口。历史预览样机仍由 opkg 导入，APK 导入 code=14；原证据见 validation-result.json。后续 APK 方向不等于该历史结果自动变为通过。

现在先完成 APK 源码、包、直接页面和后端。待后续固件提供 APK 商店支持，再核对安装、版本、APK 文件归属、登记、has_luci、相对主路由、iframe、升级、配置保护、卸载与残留；接口变更以新固件实际 schema 为准，不臆造接口。不要为补卡片而手改 appcenter UCI、缓存或 callback。在线上架仍不在范围内。

交付：源码、构建路径与命令、SDK/依赖说明、APK 与 SHA256、文件清单、目标固件、已执行结果、未测原因、已知限制。检查值只用 `pass/fail/not_run`，未知元数据用 null。

“方向确认”“主机验包通过”“本地安装可用”“业务核心通过”“商店接入通过”分别说明。技术反馈是开发方向依据；真实测试结果只能由对应固件与对应包的证据证明。本次文档更新没有新增设备安装测试，不改写原有历史结果。
