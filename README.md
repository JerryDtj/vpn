# Auto VPN

自动从阿里云 ECS 购买抢占式实例（中国香港），获取公网 IP 后自动写入 ShadowsocksX-NG 默认服务器配置。

## 功能

- 自动创建阿里云 ECS 抢占式实例（1核0.5G，1小时自动释放）
- 自动获取实例公网 IP
- 自动更新 ShadowsocksX-NG 当前激活服务器的 IP 地址
- 自动重启 ShadowsocksX-NG 使配置生效

## 环境要求

- Python 3.8+
- macOS（ShadowsocksX-NG 仅支持 macOS）
- 已安装 [ShadowsocksX-NG](https://github.com/shadowsocks/ShadowsocksX-NG/releases) 1.10.3+

## 安装

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 配置

在项目根目录创建 `.env` 文件（**该文件不会被提交到 Git**）：

```env
ALIBABA_CLOUD_ACCESS_KEY_ID=your-access-key-id
ALIBABA_CLOUD_ACCESS_KEY_SECRET=your-access-key-secret
```

> ⚠️ `.env` 文件包含敏感信息，已加入 `.gitignore`，请勿提交到版本控制。

## 使用

```bash
python auto_vpn.py
```

脚本执行流程：
1. 创建阿里云 ECS 抢占式实例（中国香港，1小时自动释放）
2. 等待实例 Running 并获取公网 IP
3. 将 IP 写入 ShadowsocksX-NG 当前激活的服务器配置
4. 重启 ShadowsocksX-NG 使新配置生效

## 项目结构

```
.
├── .env              # 阿里云 AK/SK（本地配置，不提交）
├── .gitignore        # Git 忽略规则
├── auto_vpn.py       # 主脚本
├── main.py           # 入口文件
├── requirements.txt  # Python 依赖
└── README.md         # 项目说明
```

## 注意事项

- 实例创建后 **1 小时自动释放**，请确保在有效期内使用
- 如果首选规格 `ecs.t5-lc2m1.nano` 无库存，会自动降级到 `ecs.t5-lc1m1.small`
- ShadowsocksX-NG 必须至少运行过一次并保存过服务器配置，脚本才能正常修改
