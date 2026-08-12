#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import plistlib
import pwd
import sys
import time
import subprocess
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from alibabacloud_ecs20140526.client import Client as EcsClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_ecs20140526 import models as ecs_models

# ---------- 配置 ----------
REGION_ID = "cn-hongkong"
ZONE_ID = "random"
PREFERRED_INSTANCE_TYPE = "ecs.t5-lc2m1.nano"   # 1核0.5G（正确名称）
FALLBACK_INSTANCE_TYPE = "ecs.t5-lc1m1.small"
IMAGE_ID = "m-j6ci8yhzhbgzab5c1abv"
VSWITCH_ID = "vsw-j6cnlevp6nqevwqz19jn7"
SECURITY_GROUP_ID = "sg-j6c3o5livyn7ngg1iskw"
SYSTEM_DISK_SIZE = 20
SYSTEM_DISK_CATEGORY = "cloud_efficiency"
INTERNET_MAX_BANDWIDTH_OUT = 5
SPOT_STRATEGY = "SpotAsPriceGo"
SPOT_DURATION = 1
SPOT_INTERRUPTION_BEHAVIOR = "Terminate"
INSTANCE_CHARGE_TYPE = "PostPaid"
INSTANCE_NAME = "auto-vpn-" + datetime.now().strftime("%Y%m%d%H%M")
AMOUNT = 1
CHECK_INTERVAL_SEC = 3
TIMEOUT_SEC = 180

# ShadowsocksX-NG bundle identifier
SSXNG_BUNDLE_ID = "com.qiuyuzhou.shadowsocksX-NG"

# Steamcommunity_302 进程名，请通过 `ps aux | grep -i steam` 确认后替换
STEAM_PROCESS_NAME = "Steamcommunity_302"

# ---------- 辅助 ----------
def create_ecs_client(region_id):
    ak = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID')
    sk = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
    if not ak or not sk:
        print("[ERROR] 请在 .env 或环境变量中设置 AK/SK", file=sys.stderr)
        sys.exit(1)
    config = open_api_models.Config(access_key_id=ak, access_key_secret=sk, region_id=region_id)
    return EcsClient(config)

def _run_instances_with_type(client, instance_type):
    request = ecs_models.RunInstancesRequest(
        region_id=REGION_ID,
        zone_id=ZONE_ID,
        instance_charge_type=INSTANCE_CHARGE_TYPE,
        instance_type=instance_type,
        image_id=IMAGE_ID,
        v_switch_id=VSWITCH_ID,
        security_group_id=SECURITY_GROUP_ID,
        system_disk=ecs_models.RunInstancesRequestSystemDisk(
            size=SYSTEM_DISK_SIZE,
            category=SYSTEM_DISK_CATEGORY
        ),
        auto_release_time=(datetime.now(timezone.utc) + timedelta(hours=1)).replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        internet_max_bandwidth_out=INTERNET_MAX_BANDWIDTH_OUT,
        internet_charge_type="PayByTraffic",
        spot_strategy=SPOT_STRATEGY,
        spot_duration=SPOT_DURATION,
        spot_interruption_behavior=SPOT_INTERRUPTION_BEHAVIOR,
        instance_name=INSTANCE_NAME,
        amount=AMOUNT,
        password_inherit=True,
        io_optimized="optimized",
        isp="BGP",
    )
    response = client.run_instances(request)
    instance_ids = response.body.instance_id_sets.instance_id_set
    print(f"[INFO] 实例创建成功，ID: {instance_ids[0]}", file=sys.stderr)
    return instance_ids[0]

def run_instances(client):
    try:
        return _run_instances_with_type(client, PREFERRED_INSTANCE_TYPE)
    except Exception as e:
        print(f"[WARN] 首选规格 {PREFERRED_INSTANCE_TYPE} 不可用: {e}", file=sys.stderr)
        print(f"[INFO] 自动降级到 {FALLBACK_INSTANCE_TYPE}", file=sys.stderr)
        return _run_instances_with_type(client, FALLBACK_INSTANCE_TYPE)

def wait_for_running_and_get_ip(client, instance_id):
    start_time = time.time()
    while True:
        if time.time() - start_time > TIMEOUT_SEC:
            print(f"[ERROR] 等待实例 {instance_id} 启动超时", file=sys.stderr)
            return None
        try:
            request = ecs_models.DescribeInstancesRequest(
                region_id=REGION_ID,
                instance_ids=[instance_id]
            )
            response = client.describe_instances(request)
            instances = response.body.instances.instance
            if not instances:
                time.sleep(CHECK_INTERVAL_SEC)
                continue
            inst = instances[0]
            status = inst.status
            print(f"[INFO] 实例状态: {status}", file=sys.stderr)
            if status == "Running":
                ip_obj = inst.public_ip_address
                if not ip_obj and hasattr(inst, 'eip_address') and inst.eip_address:
                    ip_obj = inst.eip_address
                if ip_obj:
                    # 尝试多种方式提取 IP
                    public_ip = None
                    # 方法1：直接访问属性（小写）
                    if hasattr(ip_obj, 'ip_address'):
                        val = ip_obj.ip_address
                        if isinstance(val, list) and len(val) > 0:
                            public_ip = val[0]
                        elif isinstance(val, str):
                            public_ip = val
                    # 方法2：访问大写属性（兼容）
                    elif hasattr(ip_obj, 'IpAddress'):
                        val = ip_obj.IpAddress
                        if isinstance(val, list) and len(val) > 0:
                            public_ip = val[0]
                        elif isinstance(val, str):
                            public_ip = val
                    # 方法3：转为字典（兜底）
                    elif isinstance(ip_obj, dict):
                        val = ip_obj.get('IpAddress')
                        if isinstance(val, list) and len(val) > 0:
                            public_ip = val[0]
                        elif isinstance(val, str):
                            public_ip = val
                    # 方法4：直接转字符串（最后尝试）
                    else:
                        public_ip = str(ip_obj)

                    if public_ip and isinstance(public_ip, str) and public_ip != '':
                        return public_ip
                    else:
                        print(f"[WARN] 提取 IP 失败: {ip_obj}，继续等待", file=sys.stderr)
                else:
                    print("[WARN] 实例 Running 但未分配公网 IP，继续等待", file=sys.stderr)
            time.sleep(CHECK_INTERVAL_SEC)
        except Exception as e:
            print(f"[ERROR] 查询状态失败: {e}", file=sys.stderr)
            time.sleep(CHECK_INTERVAL_SEC)

def _ensure_root():
    """Steamcommunity_302 是 root 进程，脚本需要以 root 运行。"""

    # 探测参数：用于检测 sudoers 是否允许免密码运行本脚本
    if len(sys.argv) > 1 and sys.argv[1] == "--_ensure_root_probe":
        sys.exit(0)

    if os.geteuid() == 0:
        return

    script_path = os.path.abspath(sys.argv[0])
    python_path = os.path.abspath(sys.executable)

    # 探测 sudoers 是否已配置（stdin 关闭，避免 sudo 等待密码输入导致卡住）
    probe = subprocess.run(
        ["sudo", "-n", python_path, script_path, "--_ensure_root_probe"],
        capture_output=True, stdin=subprocess.DEVNULL, check=False
    )
    if probe.returncode == 0:
        os.execvp("sudo", ["sudo", python_path, script_path] + sys.argv[1:])

    user = pwd.getpwuid(os.getuid()).pw_name
    print("[ERROR] 当前不是 root 用户，本脚本需要 root 权限才能停止 Steamcommunity_302。", file=sys.stderr)
    print("[INFO] 请执行以下命令配置免密码 sudo（只需一次）：", file=sys.stderr)
    print(f"        sudo sh -c 'echo \"{user} ALL=(ALL) NOPASSWD: {python_path} {script_path}, {python_path} {script_path} *\" > /etc/sudoers.d/auto_vpn'", file=sys.stderr)
    print("        sudo chmod 440 /etc/sudoers.d/auto_vpn", file=sys.stderr)
    print("[INFO] 配置完成后，重新运行本脚本即可。", file=sys.stderr)
    sys.exit(1)

def _get_steamcommunity_pids():
    """返回 Steamcommunity_302 相关进程的 PID 列表（排除当前脚本自身）。"""
    result = subprocess.run(
        ["pgrep", "-f", "-i", STEAM_PROCESS_NAME],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    own_pid = str(os.getpid())
    return [p.strip() for p in result.stdout.strip().split("\n") if p.strip() and p.strip() != own_pid]

def stop_steamcommunity_302_if_running():
    """如果 Steamcommunity_302 正在运行，则停止它。"""
    try:
        pids = _get_steamcommunity_pids()
        if not pids:
            print(f"[INFO] 未检测到 {STEAM_PROCESS_NAME} 进程", file=sys.stderr)
            return

        print(f"[INFO] 检测到 {STEAM_PROCESS_NAME}，PID: {', '.join(pids)}，正在停止", file=sys.stderr)

        # 1. 普通终止
        subprocess.run(["kill"] + pids, capture_output=True, check=False)
        time.sleep(1.5)

        # 2. 若仍在，强制终止
        pids = _get_steamcommunity_pids()
        if pids:
            subprocess.run(["kill", "-9"] + pids, capture_output=True, check=False)
            time.sleep(0.5)

        # 3. 最终校验
        pids = _get_steamcommunity_pids()
        if pids:
            print(f"[ERROR] {STEAM_PROCESS_NAME} 停止失败，残留 PID: {', '.join(pids)}", file=sys.stderr)
        else:
            print(f"[INFO] {STEAM_PROCESS_NAME} 已停止", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] 停止 {STEAM_PROCESS_NAME} 时出错: {e}", file=sys.stderr)


def update_server_ip(new_ip):
    """
    修改 ShadowsocksX-NG 当前激活（上一次连接）服务器的 ServerHost，
    并重启应用使配置生效。
    """
    # 1. 先强制停止应用，防止 cfprefsd 在内存中锁定旧配置
    subprocess.run(['killall', '-9', 'ShadowsocksX-NG'], stderr=subprocess.DEVNULL, check=False)
    subprocess.run(['killall', '-9', 'ss-local'], stderr=subprocess.DEVNULL, check=False)
    time.sleep(1.5)

    # 2. 直接读写 plist 文件
    if not os.path.exists(SSXNG_PLIST_PATH):
        print(f"[ERROR] 找不到 plist 文件: {SSXNG_PLIST_PATH}", file=sys.stderr)
        return False

    with open(SSXNG_PLIST_PATH, 'rb') as f:
        data = plistlib.load(f)

    profiles = data.get('ServerProfiles', [])
    if not profiles:
        print("[ERROR] plist 中未找到 ServerProfiles", file=sys.stderr)
        return False

    active_id = data.get('ActiveServerProfileId')
    target_index = None
    target_id = None

    # 优先匹配 ActiveServerProfileId（上一次连接的服务器）
    if active_id:
        for idx, profile in enumerate(profiles):
            if profile.get('Id') == active_id:
                target_index = idx
                target_id = active_id
                break
        if target_index is None:
            print(f"[WARN] ActiveServerProfileId={active_id} 未找到，回退到第一个服务器", file=sys.stderr)

    if target_index is None:
        target_index = 0
        target_id = profiles[0].get('Id', 'unknown')

    old_ip = profiles[target_index].get('ServerHost', '')
    profiles[target_index]['ServerHost'] = new_ip
    data['ServerProfiles'] = profiles

    if not active_id and target_id:
        data['ActiveServerProfileId'] = target_id

    with open(SSXNG_PLIST_PATH, 'wb') as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)
    print(f"[INFO] 已将服务器 IP 从 {old_ip} 更新为 {new_ip} (Id={target_id})", file=sys.stderr)

    # 3. 刷新 cfprefsd 缓存（Ventura+ 必需），清理应用缓存，重启
    _restart_shadowsocks_app()
    return True

SSXNG_PLIST_PATH = os.path.expanduser(
    f"~/Library/Preferences/{SSXNG_BUNDLE_ID}.plist")

def _restart_shadowsocks_app():
    """彻底停止 ShadowsocksX-NG，清理缓存，刷新 cfprefsd，然后重启应用"""
    support_dir = os.path.expanduser('~/Library/Application Support/ShadowsocksX-NG')
    cache_dir = os.path.expanduser('~/Library/Caches/com.qiuyuzhou.shadowsocksX-NG')
    saved_state_dir = os.path.expanduser(
        '~/Library/Saved Application State/com.qiuyuzhou.shadowsocksX-NG.savedState')

    # 强制杀死进程，确保 cfprefsd 释放对 plist 的锁定
    subprocess.run(['killall', '-9', 'ShadowsocksX-NG'], stderr=subprocess.DEVNULL, check=False)
    subprocess.run(['killall', '-9', 'ss-local'], stderr=subprocess.DEVNULL, check=False)
    time.sleep(1.5)

    # 删除动态生成文件和缓存
    for file_name in ['ss-local-config.json',
                      'com.qiuyuzhou.shadowsocksX-NG.http.plist',
                      'com.qiuyuzhou.shadowsocksX-NG.local.plist']:
        file_path = os.path.join(support_dir, file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[INFO] 已删除缓存文件: {file_path}", file=sys.stderr)

    if os.path.exists(cache_dir):
        import shutil
        shutil.rmtree(cache_dir, ignore_errors=True)
        print("[INFO] 已清理缓存目录", file=sys.stderr)

    if os.path.exists(saved_state_dir):
        import shutil
        shutil.rmtree(saved_state_dir, ignore_errors=True)
        print("[INFO] 已清理应用状态保存目录", file=sys.stderr)

    # 刷新 cfprefsd 缓存（Ventura+ 必需）
    subprocess.run(['killall', 'cfprefsd'], stderr=subprocess.DEVNULL, check=False)
    time.sleep(1.0)

    # 重新启动应用
    subprocess.Popen(['open', '-a', 'ShadowsocksX-NG'])
    print("[INFO] 已重启 ShadowsocksX-NG，请检查 UI 中的服务器 IP", file=sys.stderr)

def main():
    _ensure_root()

    # 创建实例并获取 IP
    client = create_ecs_client(REGION_ID)
    print(f"[INFO] 尝试使用首选规格 {PREFERRED_INSTANCE_TYPE}", file=sys.stderr)
    instance_id = run_instances(client)
    public_ip = wait_for_running_and_get_ip(client, instance_id)
    if not public_ip:
        print("[ERROR] 无法获取公网 IP", file=sys.stderr)
        sys.exit(1)
    print(f"[SUCCESS] 公网 IP: {public_ip}", file=sys.stderr)

    stop_steamcommunity_302_if_running()

    if not update_server_ip(public_ip):
        print("[ERROR] 修改 ShadowsocksX-NG 服务器 IP 失败", file=sys.stderr)
        sys.exit(1)

    print(public_ip)
    sys.exit(0)

if __name__ == "__main__":
    main()