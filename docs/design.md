# Dangbei Tank 本地集成设计

## 1. 背景与现状

现有逆向与桥接资产位于 `/root/iot-lab/fish-tank`。其中已经验证了以下事实：

- 鱼缸可通过本地 MQTT 直接控制
- 官方 App 与本地控制可共存
- 设备接受签发给 `emqx-endpoint.qun7.com` 的自签 TLS 证书

本方案独立定义 `dangbei_tank` 的设备模型与实体模型，不继承也不映射 Home Assistant 中任何已有鱼缸内容。

事实来源：

- [fish-tank-local-mqtt.md](/root/iot-lab/fish-tank/docs/experimental/fish-tank-local-mqtt.md)
- [fish-tank-hass-app-coexistence.md](/root/iot-lab/fish-tank/docs/experimental/fish-tank-hass-app-coexistence.md)
- [cloud-bridge-live.jsonl](/root/iot-lab/fish-tank/logs/cloud-bridge-live.jsonl)
- [mosquitto.conf](/root/iot-lab/fish-tank/.iot-local-mqtt/mosquitto.conf)

本仓库的目标是把现有实验方案整理为可发布、可部署、可维护的正式方案：

- Unraid 上运行 broker 和 gateway
- HACS 集成作为 Home Assistant 入口
- 未解协议继续通过 raw passthrough 观察

## 2. 目标与非目标

### 目标

- 定义一套可实现的运行时架构
- 固定 V1 的网关 API、实体模型与诊断能力
- 固定 Unraid 目标部署结构
- 固定 Home Assistant 集成范围与运行边界

### 非目标

- 本阶段不实现代码
- 不处理 OpenWrt / DNS 配置细节
- 不考虑 Home Assistant 中任何已有鱼缸实体、面板或自动化
- 不承诺 V1 支持未验证的定时喂食计划、附件计划或高级灯效参数

## 3. 已验证协议事实

### 3.1 设备身份

- Device label: `DANGBEI-FISH-TANK`
- MAC: `fc:01:2c:d1:9a:a8`
- IP: `192.168.199.236`
- Client ID / Username: `YUFC012CD19AA8518347`
- Password: `YU010387`
- MQTT version: `5`
- Keepalive: `60`
- Group: `YU01`

### 3.2 Topic 模型

设备订阅：

- `cmd/device/down/YUFC012CD19AA8518347`
- `config/device/down/YUFC012CD19AA8518347`
- `cmd/broadcast/down/group/YU01`
- `config/broadcast/down/group/YU01`

设备发布：

- `message/device/up/info/YUFC012CD19AA8518347`
- `message/device/up/event/YUFC012CD19AA8518347`
- `message/device/up/reply/YUFC012CD19AA8518347`

### 3.3 已确认命令

- `getAllProperties`
- `setProperty`
- `feed`

下行封包固定为：

```json
{
  "content": {
    "action": "{\"serviceName\":\"setProperty\",\"items\":{\"lightSwitch\":1}}"
  },
  "msgId": "414005920760760517",
  "type": "cmd"
}
```

上行 reply 固定为：

```json
{
  "clientId": "YUFC012CD19AA8518347",
  "type": "cmd",
  "content": {
    "action": "{\"serviceName\":\"setProperty\",\"items\":{\"lightSwitch\":1}}"
  },
  "msgId": "414005920760760517",
  "success": "true",
  "resultMsg": ""
}
```

### 3.4 已确认可读字段

已在 `getAllProperties` 中观测到：

- `lightSwitch`
- `lightMode`
- `lightBrightness`
- `lightSpeed`
- `customLightColor`
- `waterPumpSwitch`
- `waterPump`
- `waterLevelStatus`
- `temperature`
- `minTemperature`
- `maxTemperature`
- `tdsSensorValue`
- `minTdsSensorValue`
- `maxTdsSensorValue`
- `childLockSwitch`
- `buzzerSwitch`
- `customLightBrightness`
- `indLightDisplaySwitch`
- `feedingProtectionSwitch`
- `filtrationStatus`
- `waterPumpStatus`
- `reconnectDuration`
- `cultivationStatus`
- `tdsCoefficient`
- `temperatureSensorStatus`
- `peripheralNum`
- `peripheralPowerSwitch_1`
- `peripheralPowerSwitch_2`
- `powerSupplyMode`
- `tdsAlertSwitch`
- `feedPauseTime`
- `indLightDisplayMode`

已确认主灯 `lightMode` 共有 9 个灯效编号：

- `0`: 自定义
- `1`: 南美风
- `2`: 溪流风
- `3`: 夏日
- `4`: 月夜
- `5`: 珊瑚生长
- `6`: 地球自转
- `7`: 彩虹
- `8`: 光合作用

### 3.5 已确认可写字段

V1 中可直接落地的写路径分两类：

已实测成功的 `setProperty` 写入字段：

- `powerSwitch`
- `lightSwitch`
- `lightMode`
- `lightBrightness`
- `lightSpeed`
- `customLightBrightness`
- `waterPump`
- `feedingProtectionSwitch`
- `feedPauseTime`
- `peripheralPowerSwitch_1`
- `peripheralPowerSwitch_2`

已通过真实云端下行捕获、但当前 V1 暂不在 HA 中实现颜色映射的自定义灯效写法：

- `{"lightMode":0,"customLightBrightness":60,"customLightColor":"255,247,247"}`

补充说明：

- 自定义灯效仍走普通 `cmd/device/down/<client_id>` + `serviceName=setProperty`
- 当前未观测到自定义灯效依赖 `config/*` 专用 topic
- `customLightColor` 字段已纳入网关状态模型与 diagnostics 范围，后续再映射到 HA 颜色语义

已确认的独立动作命令：

- `feed`，负载为 `{"serviceName":"feed","items":{"num":1}}`

### 3.6 已确认事件

设备会直接上报局部事件：

- `{"childLockSwitch":1|0}`
- `{"powerSwitch":1|0}`
- `{"waterPump":1|2|3}`
- `{"lightSwitch":1|0}`
- `{"lightMode":0..8}`

特殊事件：

- `eventType=1`, `content={"event":4,"eventValue":"1"}`：已确认对应喂食动作；云端定时喂食下行也复用 `serviceName=feed`
- `eventType=1`, `content={"event":6,"eventValue":"0"}`：含义未确认

## 4. 目标架构

目标运行时拓扑如下：

```txt
Fish Tank
  -> MQTT/TLS to emqx-endpoint.qun7.com:8883
  -> 实际由外部 DNS 映射到 Unraid

Unraid
  -> mosquitto broker :8883
  -> fish-tank-gateway :8787
  -> fish-tank-gateway outbound MQTT to vendor cloud :8883

Home Assistant
  -> HACS integration dangbei_tank
  -> HTTP/WebSocket to fish-tank-gateway

Official App
  -> vendor cloud
  -> 由 gateway 透传云端下行到本地设备
```

设计原则：

- broker 和 gateway 不运行在 Home Assistant 内
- Home Assistant 不直接持有设备 MQTT 会话
- vendor cloud 未知操作必须透传，不能因 HA 未建模而阻断
- 状态目标是收敛，不是多主冲突仲裁

## 5. 组件职责划分

### 5.1 Broker

职责：

- 作为鱼缸的本地 MQTT TLS 入口
- 接收设备上行并向设备发送下行
- 不承担协议解析和状态管理

约束：

- 监听 `0.0.0.0:8883`
- 使用签发给 `emqx-endpoint.qun7.com` 的证书
- 初始配置沿用现有最小配置：匿名接入、TLS、stdout 日志

### 5.2 Gateway

职责：

- 本地 broker 与 vendor cloud MQTT 间的双向桥
- 已知 reply/event/snapshot 的状态归一化
- Home Assistant 命令到 vendor MQTT envelope 的转换
- 提供 HTTP 与 WebSocket API
- 保存最近 raw payload 供诊断与继续逆向

### 5.3 Home Assistant 集成

职责：

- config flow / reconfigure
- 创建实体和服务
- 消费 gateway snapshot 和状态推送
- 暴露 diagnostics

不承担：

- MQTT 连接
- 云端透传
- 协议主解析

## 6. 网关接口设计

### 6.1 HTTP API

- `GET /api/v1/devices`
  - 返回当前网关可见的设备列表
- `GET /api/v1/devices/{client_id}/state`
  - 返回设备当前 `TankState`
- `POST /api/v1/devices/{client_id}/commands`
  - 发送标准命令或 raw 命令
- `GET /api/v1/devices/{client_id}/diagnostics`
  - 返回最近 raw payload 与连通性信息

### 6.2 WebSocket API

- `GET /api/v1/ws`

事件类型固定为：

- `snapshot`
- `state_changed`
- `connectivity_changed`

### 6.3 命令请求体

```json
{
  "service_name": "setProperty",
  "items": {
    "lightSwitch": 1
  },
  "topic": null,
  "payload": null,
  "request_id": "optional-client-request-id"
}
```

约束：

- 标准集成只使用 `getAllProperties` 和 `setProperty`
- `topic` + `payload` 仅供 raw diagnostics 服务使用

### 6.4 状态模型

`TankState` 固定为：

- `identity`
  - `client_id`
  - `mac`
  - `group`
  - `sn`
  - `rom_ver_code`
- `connectivity`
  - `broker_connected`
  - `cloud_connected`
  - `device_connected`
  - `last_upstream_ts`
  - `last_snapshot_ts`
- `properties`
  - 当前已知属性集合
- `pending`
  - 待确认命令
- `dirty`
  - `needs_refresh`
  - `reason`
- `raw`
  - `last_cloud_downlink`
  - `last_local_reply`
  - `last_local_event`
  - `last_snapshot`

### 6.5 刷新策略

`getAllProperties` 触发条件固定为：

- gateway 启动后
- 设备 reconnect 后
- cloud reconnect 后
- unknown cloud downlink 后
- HA 写入成功后
- 等待设备 reply 超时后
- 周期性安全轮询，默认 `90s`

规则：

- `getAllProperties` 是唯一完整快照来源
- 上行 event 只做点更新
- 空 `resultMsg` reply 只视为 ACK
- unknown cloud downlink 必须先透传，再标记 dirty，再刷新

## 7. Home Assistant 集成设计

### 7.1 Domain 与配置模型

- domain: `dangbei_tank`
- 一个 config entry 对应一台鱼缸
- entry 配置项：
  - `gateway_base_url`
  - `api_token`
  - `client_id`
  - `display_name`
  - `area_id`

### 7.2 Config Flow

固定为两步：

1. 输入 `gateway_base_url` 与 `api_token`
2. 从 gateway 设备列表中选择鱼缸，并填写显示名与区域

同时提供 `reconfigure` 流，用于修改：

- `gateway_base_url`
- `api_token`
- `display_name`
- `area_id`

### 7.3 V1 实体

V1 固定暴露以下实体：

- `sensor`
  - `water_temperature`
  - `tds`
- `binary_sensor`
  - `water_level_ok`
  - `temperature_probe_ok`
  - `cloud_connected`
  - `device_connected`
- `switch`
  - `power`
  - `feeding_protection`
  - `accessory_1`
  - `accessory_2`
- `light`
  - `light`
    - 原生灯实体
    - 包含开关、亮度、9 个预设灯效
- `select`
  - `water_pump_mode`
- `number`
  - `feed_pause_time`
- `button`
  - `feed_now`

命名规则：

- `unique_id` 以 `client_id + key` 组成
- object ID 以 `<device_slug>_<key>` 组成
- 文档中的 key 即实现期 `entity_description.key`

### 7.4 V1 不纳入的能力

以下能力即使已观察到字段，也不进入当前 V1：

- child lock
- buzzer
- custom light color / 自定义灯效颜色面板
- 滤芯状态与寿命
- TDS 报警与系数配置
- 定时喂食计划管理
- 附件定时规则

原因：

- 写路径或业务语义仍不稳定
- 需要先通过 diagnostics 继续验证

### 7.5 集成服务

固定暴露：

- `dangbei_tank.refresh_state`
- `dangbei_tank.send_raw_command`
- `dangbei_tank.dump_last_raw_payloads`

## 8. Unraid 部署设计

### 8.1 目标目录

- Compose Manager 项目目录：`/boot/config/plugins/compose.manager/projects/dangbei-tank`
- 持久化目录：`/mnt/user/appdata/dangbei-tank`

### 8.2 目标服务

同一栈包含两个服务：

- `broker`
  - 基于 `eclipse-mosquitto:2`
  - 对外暴露 `8883`
- `gateway`
  - 基于本仓库后续构建的镜像
  - 对外暴露 `8787`

### 8.3 持久化布局

建议目录：

- `/mnt/user/appdata/dangbei-tank/mosquitto/config/`
- `/mnt/user/appdata/dangbei-tank/mosquitto/certs/`
- `/mnt/user/appdata/dangbei-tank/mosquitto/data/`
- `/mnt/user/appdata/dangbei-tank/gateway/config/`
- `/mnt/user/appdata/dangbei-tank/gateway/logs/`

### 8.4 证书材料

现有证书可直接迁移，当前观测值：

- Subject: `CN=emqx-endpoint.qun7.com`
- SAN:
  - `emqx-endpoint.qun7.com`
  - `*.qun7.com`
  - `qun7.com`

现有证书文件来源：

- `/root/iot-lab/fish-tank/.iot-local-mqtt/certs/server.crt`
- `/root/iot-lab/fish-tank/.iot-local-mqtt/certs/server.key`

## 9. 诊断、可观测性与故障处理

### 9.1 诊断能力

gateway 必须保留：

- 最近一次 cloud downlink
- 最近一次 local reply
- 最近一次 local event
- 最近一次 snapshot
- 当前连通性状态
- 最近 refresh 原因

集成必须通过 `diagnostics.py` 提供脱敏后的诊断输出，至少脱敏：

- API token
- MQTT password
- 任何可能复用的云端凭据

### 9.2 预期故障行为

- HA 重启：
  - gateway 与 App 不应受影响
  - HA 实体重新订阅后恢复
- vendor cloud 不可达：
  - 本地已知命令仍可工作
  - 官方 App 不可用
- gateway 不可达：
  - HA 实体转为 unavailable
  - App 共存路径失效
- broker 不可达：
  - 鱼缸断开本地入口
  - HA 与 App 共存同时失败

## 10. V1 范围与后续扩展

### 10.1 V1 范围

- broker + gateway + HACS 集成的完整闭环
- 已知字段的稳定读写
- raw diagnostics
- 官方 App 共存

### 10.2 后续扩展

- 自定义灯效颜色能力
- 灯效速度独立控制
- child lock / buzzer / no disturb
- 滤芯寿命
- TDS 相关高级配置
- 定时喂食计划与附件计划

## 11. 验收标准

设计验收通过的标准：

- 文档足以直接指导实现
- 所有关键接口和实体边界已固定
- 已明确哪些能力进入 V1，哪些不进入
- 已明确 Unraid 部署目标目录与服务划分
- 已明确该方案与 Home Assistant 中任何既有鱼缸内容无关

实现阶段的最小验收标准预留如下：

- 鱼缸接入 Unraid broker
- gateway 可拉取并维护稳定状态
- HACS 集成成功创建 config entry
- V1 实体全部可读写
- 官方 App 与 HA 可并存控制

## 13. 待确认 / 暂不处理项

- `customLightColor` 的语义化映射与 HA 颜色模型适配
- `event=6` 的实际含义
- 定时喂食计划与附件定时是否走 MQTT 之外的云端 HTTP 路径
